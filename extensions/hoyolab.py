import asyncio
import dataclasses as dc
import datetime as dt

import discord
import discord.ext.commands as cmd
import genshin
from discord.ext.tasks import loop

import database as db
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


class CookieModal(discord.ui.Modal):
    def __init__(
        self,
        *children: discord.ui.InputText,
        title: str,
        v2: bool = True,
    ):
        super().__init__(*children, title=title)
        self.v2 = v2
        self.add_item(
            discord.ui.InputText(label="Account ID", placeholder="account_id")
        )
        self.add_item(
            discord.ui.InputText(
                label="Cookie Token", placeholder="cookie_token"
            )
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        account_id = self.children[0].value
        cookie_token = self.children[1].value
        try:
            account_id = int(account_id)
        except ValueError:
            await interaction.followup.send(
                ephemeral=True,
                embed=utils.make_error(
                    "Invalid Account Id",
                    "The `account_id` you entered does not seem correct "
                    "(due to not being a base 10 number) was discarded.",
                ),
            )
            return

        if data := await HoyoLabData.load(interaction.user.id, decrypt=False):
            data.account_id = account_id
            data.cookie_token = cookie_token
            data.v2 = self.v2
        else:
            data = HoyoLabData(
                discord_snowflake=interaction.user.id,
                _account_id=int(account_id),
                cookie_token=cookie_token,
                v2=self.v2,
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


class CookieView(discord.ui.View):
    instructions = (
        "1. Go to https://hoyolab.com/.\n"
        "2. Login to your account.\n"
        "3. Open Developer Tools:\n"
        " - `F12`\n"
        " - `Ctrl` + `Shift` + `I`\n"
        " - Menu > More Tools > (Web) Developer Tools\n"
        "4. Find Cookies:\n"
        " - (Chrome) Go to Application > Cookies > `https://www.hoyolab.com`.\n"
        " - (Firefox) Go to Storage > Cookies > `https://www.hoyolab.com`.\n"
        "5. Copy Cookies (which ever set is available):\n"
        " - `account_id` and `cookie_token` (v1 Cookies)\n"
        " - `account_id_v2` and `cookie_token_v2` (v2 Cookies)\n"
        "6. Press the Button for which cookies you have and fill in the modal.\n"
    )

    @classmethod
    def make_instruction_embed(cls, **kwargs):
        return utils.make_embed(
            title="Cookie Instructions",
            desc=cls.instructions,
            **kwargs,
        )

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

    def __init__(self, datas: list[HoyoLabData]):
        super().__init__()
        self.account: HoyoLabData | None = None
        self.accounts = datas[:25]  # Limit of Discord
        select_account: discord.ui.Select = self.get_item("account_select")
        for i, account in enumerate(self.accounts):
            select_account.add_option(label=account.account_id, value=str(i))

    @discord.ui.select(
        placeholder="Select an Account", custom_id="account_select", row=0
    )
    async def select_account(
        self, select: discord.ui.Select, interaction: discord.Interaction
    ):
        self.account = self.accounts[int(select.values[0])]
        select.placeholder = self.account.account_id
        self.enable_all_items()
        select.disabled = True
        self.set_button_emoji(
            self.get_item("checkin"), self.account.auto_daily
        )
        self.set_button_emoji(self.get_item("codes"), self.account.auto_codes)
        # await self.select_game(select_game, interaction)
        await interaction.response.edit_message(view=self)

    def set_button_emoji(self, button: discord.ui.Button, enabled: bool):
        if enabled:
            button.emoji = self.ENABLED_EMOJI
        else:
            button.emoji = self.DISABLED_EMOJI

    @discord.ui.button(
        label="Daily Check-In", custom_id="checkin", disabled=True, row=2
    )
    async def toggle_daily(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        self.account.auto_daily = not self.account.auto_daily
        self.set_button_emoji(button, self.account.auto_daily)
        await interaction.response.edit_message(view=self)

    @discord.ui.button(
        label="Receive Codes", custom_id="codes", disabled=True, row=2
    )
    async def toggle_codes(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        self.account.auto_codes = not self.account.auto_codes
        self.set_button_emoji(button, self.account.auto_codes)
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Discard Changes", disabled=True, row=3)
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
        disabled=True,
        row=3,
    )
    async def save(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        self.disable_all_items()
        button.emoji = self.ENABLED_EMOJI
        await interaction.response.edit_message(view=self)
        self.stop()
        await self.account.save()


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

    @configure_cmds.command()
    @utils.autogenerate_options
    async def delete(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        await HoyoLabData.delete(ctx.author.id)
        await ctx.respond(
            embed=utils.make_embed(
                "Data Deleted",
                "Your settings and HoyoLab cookies have been deleted.",
                ctx,
            )
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
        await ctx.respond(view=SettingsView(data))

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
            f"{failed_to_claim}. Unknown exception `{type(e)}",
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
    embed = utils.make_embed(f"Account Settings for `{data.account_id}`", "")
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
