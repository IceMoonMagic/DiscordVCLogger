import asyncio
import dataclasses as dc
import datetime as dt

import discord
import discord.ext.commands as cmd
import genshin
from discord.ext.tasks import loop

import database as db
import discord_menus
import utils

logger = db.get_logger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info(f"Loading Cog: {__name__}")
    bot.add_cog(HoyoLab(bot))
    auto_redeem_daily.start(bot)


def teardown(bot: cmd.Bot):
    """Removes the cog from the bot"""
    logger.info("Unloading Cog: HoyoLab Cog")
    bot.remove_cog(HoyoLab.qualified_name)
    auto_redeem_daily.stop()


@dc.dataclass
class HoyoLabData(db.Storable):
    primary_key_name = "_account_id"

    encrypt_attrs = ["cookie_token"]

    discord_snowflake: int
    _account_id: int
    cookie_token: str
    nickname: str = ""
    v2: bool = True  # if using v2 Cookies
    # ToDo: Implement for each `genshin.Game` (Genshin, Honkai3rd, Starrail)
    auto_daily: bool = True
    auto_codes: bool = True

    @property
    def snowflake(self) -> int:
        return self.discord_snowflake

    @property
    def account_id(self) -> str:
        return str(self._account_id)

    @account_id.setter
    def account_id(self, account_id: int | str):
        self._account_id = int(account_id)

    @property
    def cookies(self) -> dict[str, str]:
        if self.v2:
            return {
                "account_id_v2": self.account_id,
                "cookie_token_v2": self.cookie_token,
            }
        return {
            "account_id": self.account_id,
            "cookie_token": self.cookie_token,
        }

    @property
    def settings(self) -> dict[str, bool]:
        return {
            "auto_daily": self.auto_daily,
            "auto_codes": self.auto_codes,
        }

    @property
    def display_name(self) -> str:
        if self.nickname:
            return f"{self.nickname} ({self.account_id})"
        else:
            return f"{self.account_id}"


class CookieModal(discord.ui.Modal):
    def __init__(
        self,
        *children: discord.ui.InputText,
        title: str,
        v2: bool = True,
    ):
        super().__init__(*children, title=title)
        self.v2 = v2
        v2_str = "_v2" if v2 else ""
        self.add_item(
            discord.ui.InputText(
                label="Account ID", placeholder="account_id" + v2_str
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="Cookie Token", placeholder="cookie_token" + v2_str
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="Nickname (Optional)",
                placeholder='e.g. "Main Genshin"',
                required=False,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        account_id = self.children[0].value
        cookie_token = self.children[1].value
        nickname = self.children[2].value or ""
        try:
            account_id = int(account_id)
        except ValueError:
            await interaction.followup.send(
                ephemeral=True,
                embed=utils.make_error(
                    "Invalid Account Id",
                    "The `account_id` you entered does not seem correct "
                    "(due to not being a base 10 number) and was discarded.",
                ),
            )
            return

        count, data = 0, None
        for account in await HoyoLabData.load_all(
            decrypt=False, discord_snowflake=interaction.user.id
        ):
            if account.account_id == account_id:
                data = account
                break
            count += 1

        if data:
            data.account_id = account_id
            data.cookie_token = cookie_token
            data.v2 = self.v2
        elif count >= 25:
            await interaction.followup.send(
                ephemeral=True,
                embed=utils.make_error(
                    "Too Many Accounts",
                    "This account could not be processed "
                    "as it would put you past the limit of 25.",
                ),
            )
            return
        else:
            data = HoyoLabData(
                discord_snowflake=interaction.user.id,
                _account_id=int(account_id),
                cookie_token=cookie_token,
                v2=self.v2,
                nickname=nickname,
            )

        if check := await _check_cookies(data):
            await data.save()

            # Disable old View
            original_message = await interaction.original_response()
            view = discord.ui.View.from_message(original_message)
            view.disable_all_items()
            view.stop()
            await original_message.edit(view=view)

        await interaction.followup.send(
            ephemeral=True,
            embed=check,
        )


class NicknameModal(discord.ui.Modal):
    def __init__(self, data: HoyoLabData):
        super().__init__(title=f"Change Nickname of `{data.display_name}`")
        self.data = data
        self.add_item(
            discord.ui.InputText(
                label="Nickname (Optional)",
                placeholder='e.g. "Main Genshin"',
                required=False,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        self.data.nickname = self.children[0].value or ""
        await self.data.save()

        await interaction.followup.send(
            ephemeral=True,
            embed=utils.make_embed(
                "Nickname Updated",
                f"Nickname for {self.data.account_id} "
                f"is now {self.data.nickname}.",
            ),
        )

    @classmethod
    async def send(cls, data: HoyoLabData, interaction: discord.Interaction):
        await interaction.response.send_modal(cls(data))


class CookieView(discord.ui.View):
    instructions = (
        "1. Go to https://hoyolab.com/.\n"
        "2. Login to your account.\n"
        "3. Open Developer Tools:\n"
        " - Menu > More Tools > (Web) Developer Tools\n"
        " - OR `F12`\n"
        " - OR `Ctrl` + `Shift` + `I`\n"
        "4. Go to the Cookie Section:\n"
        " - (Chrome) Go to Application > Cookies > `https://www.hoyolab.com`.\n"
        " - (Firefox) Go to Storage > Cookies > `https://www.hoyolab.com`.\n"
        "5. Copy Cookies (which ever set is available):\n"
        " > Using an already used `account_id(_v2)` will update the entry\n"
        " - `account_id` and `cookie_token` (v1 Cookies)\n"
        " - `account_id_v2` and `cookie_token_v2` (v2 Cookies)\n"
        "6. Press the button for which cookies you have and fill in the modal.\n"
        "> If you get `Invalid Cookie Data` while you're sure they're correct,\n"
        "> try signing out and back in or clearing your site cookies / data."
    )

    @classmethod
    def make_instruction_embed(cls, **kwargs) -> discord.Embed:
        return utils.make_embed(
            title="Cookie Instructions",
            desc=cls.instructions,
            **kwargs,
        )

    @staticmethod
    def make_limit_embed(existing: int = None, **kwargs) -> discord.Embed:
        embed = utils.make_embed(
            "Note on Account Limit",
            "Due to a limitation of Discord's dropdown menus, "
            "each Discord Account can only have 25 HoyoLab Accounts.",
            **kwargs,
        )
        if existing is not None:
            embed.add_field(
                name="Existing Accounts",
                value=f"You have `{existing}`/`25` existing accounts.",
            )
        return embed

    def __init__(self, *items: discord.ui.Item):
        super().__init__(*items)
        link_button = discord.ui.Button(
            label="HoyoLab",
            url="https://www.hoyolab.com",
            style=discord.ButtonStyle.link,
        )
        self.add_item(link_button)

    @discord.ui.button(label="I have v1 Cookies")
    async def v1_cookies(
        self, _button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.send_modal(
            CookieModal(title="HoyoLab Cookies", v2=False)
        )

    @discord.ui.button(label="I have v2 Cookies")
    async def v2_cookies(
        self, _button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.send_modal(
            CookieModal(title="HoyoLab Cookies v2", v2=True)
        )


class SettingsView(discord.ui.View):
    ENABLED_EMOJI = "✅"  # ✔
    DISABLED_EMOJI = "❎"  # ✖

    def __init__(self, data: HoyoLabData):
        super().__init__()
        self.account = data
        self.add_item(
            discord_menus.DBToggleButton(
                "auto_daily", data, label="Daily Check-In"
            )
        )
        self.add_item(
            discord_menus.DBToggleButton(
                "auto_codes", data, label="Receive Codes"
            )
        )

    @discord.ui.button(label="Discard Changes", row=1)
    async def discard(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        self.disable_all_items()
        button.emoji = self.ENABLED_EMOJI
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(
        label="Save Changes",
        style=discord.ButtonStyle.success,
        row=1,
    )
    async def save(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        self.disable_all_items()
        button.emoji = self.ENABLED_EMOJI
        await interaction.response.edit_message(view=self)
        self.stop()
        await self.account.save()

    @classmethod
    async def send(cls, data: HoyoLabData, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=cls.make_embed(data), ephemeral=True, view=cls(data)
        )

    @staticmethod
    def make_embed(data: HoyoLabData) -> discord.Embed:
        code_share_name = HoyoLab.share.name
        command = HoyoLab.share.parent
        while command is not None:
            code_share_name = f"{command.name} {code_share_name}"
            command = command.parent

        return (
            utils.make_embed(
                f"Settings for `{data.display_name}`",
                # f"{discord_menus.ToggleButton.TRUE_EMOJI} "
                # f"- Setting Enabled\n"
                # f"{discord_menus.ToggleButton.FALSE_EMOJI} "
                # f"- Setting Disabled",
            )
            .add_field(
                name="Daily Check-In",
                value="Allow the bot to automatically "
                "redeem your HoyoLab Daily Check-In",
            )
            .add_field(
                name="Receive Codes",
                value="Allow the bot to redeem gift codes "
                f"shared by /{code_share_name}",
            )
        )


class HoyoLab(cmd.Cog):
    def __init__(self, bot: cmd.Bot):
        self.bot = bot

    hoyolab_cmds = discord.SlashCommandGroup("hoyo", "foo")

    daily_rewards_cmds = hoyolab_cmds.create_subgroup(
        "daily", "Relating to HoyoLab Daily Check-In"
    )

    redeem_codes_cmds = hoyolab_cmds.create_subgroup(
        "code", "Relating to Genshin Gift Codes"
    )

    configure_cmds = hoyolab_cmds.create_subgroup("config")

    # ToDo: Verify game account exists
    game_selection = discord.Option(
        genshin.Game, "The game to run the command for."
    )

    @cmd.Cog.listener("on_ready")
    async def unlock_reminder(self):
        await asyncio.sleep(5 * 60)
        if HoyoLabData.box is None:
            for user_id in self.bot.owner_ids or [self.bot.owner_id]:
                dm = await utils.get_dm(user_id, self.bot)
                await dm.send(
                    embed=utils.make_embed(
                        "Unlock HoyoLabData",
                        "The bot is ready, but HoyoLabData "
                        "still can't be encrypted/decrypted.",
                    )
                )

    @daily_rewards_cmds.command()
    @utils.autogenerate_options
    async def redeem_daily(
        self, ctx: discord.ApplicationContext, game: game_selection
    ):
        """
        Manually redeem your daily check-in.

        :param ctx: Application Context form Discord.
        :param game: The game to run the command for.
        """
        await ctx.defer(ephemeral=True)
        if not (client := await _get_client(ctx.author.id, game=game)):
            await ctx.respond(embed=client)

        await ctx.respond(embed=await _redeem_daily(client))

    @redeem_codes_cmds.command()
    @utils.autogenerate_options
    async def redeem(
        self, ctx: discord.ApplicationContext, code: str, game: game_selection
    ):
        """
        Redeem a code for yourself.

        :param ctx: Application Context form Discord.
        :param code: Code to redeem.
        :param game: The game to run the command for.
        """
        await ctx.defer(ephemeral=True)

        code = code.strip().upper()

        if not (client := await _get_client(ctx.author.id, game=game)):
            await ctx.respond(embed=client)
            return
        await ctx.respond(embed=await _redeem_code(client, code))

    @redeem_codes_cmds.command()
    @utils.autogenerate_options
    async def share(
        self, ctx: discord.ApplicationContext, code: str, game: game_selection
    ):
        """
        Redeem a code for everyone with `auto_codes` enabled.

        :param ctx: Application Context form Discord.
        :param code: Code to redeem.
        :param game: The game to run the command for.
        """

        await ctx.defer()

        code = code.strip().upper()

        if not (client := await _get_client(ctx.author.id, game=game)):
            await ctx.respond(embed=client)
            return
        if (
            not (embed := await _redeem_code(client, code))
            and "claimed" not in embed.description
        ):
            await ctx.respond(
                embed=utils.make_embed(
                    "Code Share Aborted",
                    f"Not sharing code due to the following error:\n"
                    f">>> {embed.description}",
                    embed=embed,
                )
            )
            return

        with asyncio.TaskGroup() as tg:
            tg.create_task(utils.send_dm(ctx.author.id, ctx.bot, embed=embed))

            async for person in HoyoLabData.load_gen(auto_codes=True):
                if person.snowflake == ctx.author.id:
                    continue

                client = _make_client(person)
                tg.create_task(
                    utils.do_and_dm(
                        user_id=person.snowflake,
                        bot=ctx.bot,
                        coro=_redeem_code(client, code),
                        send=True,
                    )
                )

            tg.create_task(
                ctx.respond(
                    embed=utils.make_embed(
                        "Sharing Code", f"`{code}` has been shared.", ctx
                    )
                )
            )

    @configure_cmds.command()
    @utils.autogenerate_options
    async def check(self, ctx: discord.ApplicationContext):
        """Check your settings and cookie status."""
        await ctx.defer(ephemeral=True)

        await ctx.respond(embed=await _check_cookies(ctx.author.id))

    @configure_cmds.command()
    @utils.autogenerate_options
    async def cookies(self, ctx: discord.ApplicationContext):
        """Set your HoyoLab cookies."""
        await ctx.respond(
            embed=CookieView.make_instruction_embed(),
            ephemeral=True,
            view=CookieView(),
        )
        count = len(
            await HoyoLabData.load_all(False, discord_snowflake=ctx.author.id)
        )
        await ctx.respond(
            ephemeral=True, embed=CookieView.make_limit_embed(count)
        )

    @configure_cmds.command()
    async def nickname(self, ctx: discord.ApplicationContext):
        """Change the nickname for a HoyoLab Account."""
        data = await HoyoLabData.load_all(discord_snowflake=ctx.author.id)
        if len(data) == 0:
            await ctx.respond(
                ephemeral=True,
                embed=utils.make_embed(
                    "No Accounts", "No accounts to set nicknames for."
                ),
            )
            return

        await ctx.respond(
            ephemeral=True,
            view=discord_menus.DBSelector(
                data, NicknameModal.send, label_key=lambda d: d.display_name
            ),
        )

    @configure_cmds.command()
    @utils.autogenerate_options
    async def delete(self, ctx: discord.ApplicationContext):
        data = await HoyoLabData.load_all(
            decrypt=False, discord_snowflake=ctx.author.id
        )
        if len(data) == 0:
            await ctx.respond(
                ephemeral=True,
                embed=utils.make_embed(
                    "No Accounts", "No accounts to delete."
                ),
            )
            return

        async def _del(_data: HoyoLabData, interaction: discord.Interaction):
            display_name = _data.display_name
            await HoyoLabData.delete(getattr(_data, _data.primary_key_name))
            await interaction.response.send_message(
                ephemeral=True,
                embed=utils.make_embed(
                    f"Data for `{display_name}` Deleted",
                    "Your settings and HoyoLab cookies have been deleted.",
                    ctx,
                ),
            )

        await ctx.respond(
            ephemeral=True,
            view=discord_menus.DBSelector(
                data, _del, label_key=lambda d: d.display_name
            ),
        )

    @configure_cmds.command()
    @utils.autogenerate_options
    async def settings(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        data = await HoyoLabData.load_all(discord_snowflake=ctx.author.id)
        if len(data) == 0:
            await ctx.respond(
                embed=utils.make_embed(
                    "No Accounts",
                    "No accounts to show settings for. "
                    "You can add some with `/hoyo config cookies`",
                )
            )
        await ctx.respond(
            view=discord_menus.DBSelector(
                data, SettingsView.send, label_key=lambda d: d.display_name
            )
        )

    @cmd.is_owner()
    @hoyolab_cmds.command()
    async def unlock(self, ctx: discord.ApplicationContext):
        await ctx.send_modal(utils.UnlockModal(HoyoLabData))

    @cmd.is_owner()
    @hoyolab_cmds.command()
    async def lock(self, ctx: discord.ApplicationContext):
        HoyoLabData.clear_key()
        await ctx.respond(
            embed=utils.make_embed("HoyoLabData Locked", ctx=ctx),
            ephemeral=True,
        )

    @cmd.is_owner()
    @daily_rewards_cmds.command()
    async def induce_auto_redeem(self, ctx: discord.ApplicationContext):
        await ctx.respond("Triggering `auto_redeem-daily`.")
        await auto_redeem_daily(ctx.bot)


CHECKIN_ICON = db.get_json_data(__name__).get("check-in icon", "")


def _make_client(
    data: HoyoLabData, game: genshin.Game = genshin.Game.GENSHIN
) -> genshin.Client:
    client = genshin.Client(game=game)
    client.set_cookies(data.cookies)
    return client


async def _get_data(snowflake) -> HoyoLabData | utils.ErrorEmbed:
    if isinstance(data := await HoyoLabData.load(snowflake), HoyoLabData):
        return data
    return utils.make_error(
        "Failed to Retrieve User Data",
        "Please configure your information using "
        "`/hoyo configure cookies`.",
    )


async def _get_client(
    snowflake: int, game: genshin.Game = genshin.Game.GENSHIN
) -> genshin.Client | utils.ErrorEmbed:
    if isinstance(data := await _get_data(snowflake), HoyoLabData):
        return _make_client(data, game)
    return data


async def _redeem_daily(
    client: genshin.Client, ctx: discord.ApplicationContext = None
) -> discord.Embed:
    failed_to_claim = f"Failed to claim daily rewards for {client.game.name}"
    try:
        reward = await client.claim_daily_reward()
        embed = utils.make_embed(
            "Daily Rewards Claimed", f"{reward.amount}x {reward.name}", ctx
        )
        embed.set_thumbnail(url=reward.icon)
        embed.set_author(name="HoyoLab Daily Check-In", icon_url=CHECKIN_ICON)
        return embed
    except genshin.AlreadyClaimed:
        return utils.make_error(
            "Daily Rewards Already Claimed",
            f"{failed_to_claim} as " "they have already been claimed.",
        )
    except genshin.InvalidCookies:
        return utils.make_error(
            "Invalid Cookies",
            f"{failed_to_claim} as saved cookies are invalid",
        )
    except genshin.GeetestTriggered:
        return utils.make_error(
            "Geetest Triggered",
            f"{failed_to_claim} as "
            "a GeeTest Captcha was triggered. "
            "It is unclear what the best way to fix this is. "
            "For now, you will have to manually redeem them at "
            "[HoyoLab](www.hoyolab.com).",
        )
    except Exception as e:
        return utils.make_error(
            "Unknown Exception",
            f"{failed_to_claim}. Unknown exception `{type(e)}`",
        )


# @loop(time=dt.time(0, 5, 5, tzinfo=dt.timezone(dt.timedelta(hours=8))))
@loop(time=dt.time(16, 15, 5))
async def auto_redeem_daily(bot: cmd.Bot):
    logger.info("Automatically claiming daily rewards.")
    from random import randint

    async def _auto_redeem_daily(**kwargs):
        await asyncio.sleep(randint(0, 900))
        await utils.do_and_dm(**kwargs)

    async with asyncio.TaskGroup() as tg:
        async for person in HoyoLabData.load_gen(auto_daily=True):
            for account in await _make_client(person).get_game_accounts():
                client = _make_client(person, account.game)
                tg.create_task(
                    _auto_redeem_daily(
                        user_id=person.snowflake,
                        bot=bot,
                        coro=_redeem_daily(client),
                        send=True,
                    )
                )


async def _redeem_code(
    client: genshin.Client, code: str, tries: int = 0
) -> discord.Embed | utils.ErrorEmbed:
    try:
        await client.redeem_code(code)
        return utils.make_embed(
            "Successfully Redeemed Code", f"Successfully redeemed `{code}`."
        )
    except genshin.RedemptionInvalid as e:
        return utils.make_error(
            "Failed to Redeem Code", f"Could not redeem `{code}`. {e.msg}"
        )
    except genshin.RedemptionClaimed:
        return utils.make_error(
            "Failed to Redeem Code", f"Code `{code}` claimed already."
        )
    except genshin.RedemptionCooldown:
        if tries < 3:
            await asyncio.sleep(tries + 1)
            return await _redeem_code(client, code, tries + 1)
        return utils.make_error(
            "Failed to Redeem Code", f"Redemption on cooldown.\nCode: `{code}`"
        )


async def _check_cookies(
    data: HoyoLabData,
) -> discord.Embed | utils.ErrorEmbed:
    client = _make_client(data)
    try:
        accounts = await client.get_game_accounts()
    except genshin.CookieException:
        return utils.make_error(
            "Invalid Cookie Data",
            "Unable to login to HoyoLab with your cookies.",
        )

    embed = utils.make_embed("Account Successfully Connected", "")
    for account in accounts:
        values = ""
        for k, v in dict(account).items():
            values += f'{k.replace("_", " ").title()}: `{v}`\n'
        embed.add_field(
            name=account.game.name, value=values.strip(), inline=False
        )
    return embed


def _check_settings(data: HoyoLabData) -> discord.Embed:
    embed = utils.make_embed(f"Account Settings for `{data.display_name}`", "")
    for name, value in data.settings.items():
        for option in HoyoLab.settings.options:
            if name == option.name:
                embed.add_field(
                    name=f"{name} (`{value}`)",
                    value=option.description,
                    inline=False,
                )
                break
    return embed
