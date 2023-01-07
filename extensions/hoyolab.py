import asyncio
import dataclasses as dc
import datetime as dt

import discord
import discord.ext.commands as cmd
import genshin
from discord.ext.tasks import loop

import database as db
import system

logger = db.get_logger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info(f'Loading Cog: {__name__}')
    bot.add_cog(HoyoLab(bot))
    auto_redeem_daily.start(bot)


def teardown(bot: cmd.Bot):
    """Removes the cog from the bot"""
    logger.info('Unloading Cog: HoyoLab Cog')
    bot.remove_cog(HoyoLab.qualified_name)
    auto_redeem_daily.stop()


@dc.dataclass
class HoyoLabData(db.Storable):
    primary_key_name = 'discord_snowflake'
    table_name = 'GenshinData'

    encrypt_attrs = ['account_id', 'cookie_token', 'ltuid', 'ltoken']

    discord_snowflake: int
    account_id: str
    cookie_token: str
    ltuid: str
    ltoken: str
    auto_daily: bool = True
    auto_codes: bool = True
    notif_daily: bool = True
    notif_codes: bool = True

    @property
    def snowflake(self) -> int:
        return self.discord_snowflake

    @property
    def cookies(self) -> dict[str, str]:
        return {'account_id': self.account_id,
                'cookie_token': self.cookie_token,
                'ltuid': self.ltuid,
                'ltoken': self.ltoken}

    @property
    def settings(self) -> dict[str, bool]:
        return {'auto_daily': self.auto_daily,
                'auto_codes': self.auto_codes,
                'notif_daily': self.notif_daily,
                'notif_codes': self.notif_codes}


class CookieModal(discord.ui.Modal):

    def __init__(self, *children: discord.ui.InputText,
                 title: str, bot: cmd.Bot):
        super().__init__(*children, title=title)
        self.bot = bot
        self.add_item(discord.ui.InputText(
            label='Account ID',
            placeholder='account_id'))
        self.add_item(discord.ui.InputText(
            label='Cookie Token',
            placeholder='cookie_token'))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        cookies = {'account_id': self.children[0].value,
                   'cookie_token': self.children[1].value}
        try:
            cookies.update(await genshin.complete_cookies(cookies))
        except genshin.CookieException:
            await interaction.followup.send(
                ephemeral=True,
                embed=system.make_error(
                    'Invalid Cookie Data',
                    'The cookie data you entered '
                    'did not work and was discarded.'))
            return

        if data := await HoyoLabData.load(interaction.user.id, decrypt=False):
            await data.update(**cookies).save()
        else:
            await HoyoLabData(interaction.user.id, **cookies).save()

        await interaction.followup.send(
            ephemeral=True,
            embed=await _check(
                interaction.user.id,
                color=interaction.guild.me.color
                if interaction.guild else None))


class HoyoLab(cmd.Cog):

    def __init__(self, bot: cmd.Bot):
        self.bot = bot

    genshin_cmds = discord.SlashCommandGroup("genshin", "foo")

    daily_rewards_cmds = genshin_cmds.create_subgroup(
        'daily', 'Relating to HoyoLab Daily Check-In')

    redeem_codes_cmds = genshin_cmds.create_subgroup(
        'code', 'Relating to Genshin Gift Codes')

    configure_cmds = genshin_cmds.create_subgroup('config')

    @cmd.Cog.listener('on_ready')
    async def unlock_reminder(self):
        if HoyoLabData.box is None:
            for user_id in self.bot.owner_ids or [self.bot.owner_id]:
                dm = await system.get_dm(user_id, self.bot)
                await dm.send(embed=system.make_embed(
                    'Unlock HoyoLabData',
                    'The bot is ready, but HoyoLabData '
                    'still can\'t be encrypted/decrypted.'))

    @daily_rewards_cmds.command()
    @system.autogenerate_options
    async def redeem_daily(self, ctx: discord.ApplicationContext):
        """
        Manually redeem your daily check-in.

        :param ctx: Application Context form Discord.
        """
        await ctx.defer(ephemeral=True)
        if not (client := await _get_client(ctx.author.id)):
            await ctx.respond(embed=client)

        await ctx.respond(embed=await _redeem_daily(client))

    @redeem_codes_cmds.command()
    @system.autogenerate_options
    async def redeem(self, ctx: discord.ApplicationContext, code: str):
        """
        Redeem a code for yourself.

        :param ctx: Application Context form Discord.
        :param code: Code to redeem.
        """
        await ctx.defer(ephemeral=True)

        code = code.strip().upper()

        if not (client := await _get_client(ctx.author.id)):
            await ctx.respond(embed=client)
            return
        await ctx.respond(embed=await _redeem_code(client, code))

    @redeem_codes_cmds.command()
    @system.autogenerate_options
    async def share(self, ctx: discord.ApplicationContext, code: str):
        """
        Redeem a code for everyone with `auto_codes` enabled.

        :param ctx: Application Context form Discord.
        :param code: Code to redeem.
        """

        await ctx.defer()

        code = code.strip().upper()

        if not (client := await _get_client(ctx.author.id)):
            await ctx.respond(embed=client)
            return
        if not (embed := await _redeem_code(client, code)) and \
                'claimed' not in embed.description:
            await ctx.respond(embed=system.make_embed(
                'Code Share Aborted',
                f'Not sharing code due to the following error:\n'
                f'>>> {embed.description}',
                embed=embed))
            return

        elif (await HoyoLabData.load(ctx.author.id)).notif_codes:
            tasks = [asyncio.create_task(
                system.send_dm(ctx.author.id, ctx.bot, embed=embed))]
        else:
            tasks = []  # Python 3.11: ToDo: asyncio.TaskGroup
        async for person in HoyoLabData.load_gen(auto_codes=True):
            if person.snowflake == ctx.author.id:
                continue

            client = _make_client(person)
            tasks.append(asyncio.create_task(system.do_and_dm(
                user_id=person.snowflake,
                bot=ctx.bot,
                coro=_redeem_code(client, code),
                send=person.notif_codes)))

        await ctx.respond(embed=system.make_embed(
            'Sharing Code',
            f'`{code}` has been shared.',
            ctx))

        for task in tasks:
            await task

    @configure_cmds.command()
    @system.autogenerate_options
    async def check(self, ctx: discord.ApplicationContext):
        """Check your settings and cookie status."""
        await ctx.defer(ephemeral=True)

        await ctx.respond(embed=await _check(ctx.author.id, ctx))

    @configure_cmds.command()
    @system.autogenerate_options
    async def cookies(self, ctx: discord.ApplicationContext):
        """Set your HoyoLab cookies."""
        await ctx.send_modal(CookieModal(title='HoyoLab Cookies', bot=ctx.bot))

    @configure_cmds.command()
    @system.autogenerate_options
    async def delete(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        await HoyoLabData.delete(ctx.author.id)
        await ctx.respond(embed=system.make_embed(
            'Data Deleted',
            'Your settings and HoyoLab cookies have been deleted.',
            ctx))

    @configure_cmds.command()
    @system.autogenerate_options
    async def settings(self, ctx: discord.ApplicationContext,
                       auto_daily: bool = None,
                       auto_codes: bool = None,
                       notif_daily: bool = None,
                       notif_codes: bool = None):
        """
        Configure settings for interactions with HoyoLab.

        :param ctx: Application context from Discord.
        :param bool auto_daily: Allow the bot to automatically redeem your
        HoyoLab daily check-in.
        :param auto_codes: Allow the bot to redeem codes others share with the
        share_codes command.
        :param notif_daily: Receive DMs for automatically claimed
        daily check-in rewards.
        :param notif_codes: Receive DMs for automatically claimed gift codes.
        """
        await ctx.defer(ephemeral=True)
        if isinstance(data := await HoyoLabData.load(ctx.author.id),
                      HoyoLabData):
            data.auto_daily = auto_daily \
                if auto_daily is not None else data.auto_daily
            data.auto_codes = auto_codes \
                if auto_codes is not None else data.auto_codes
            data.notif_daily = notif_codes \
                if notif_daily is not None else data.notif_daily
            data.notif_codes = notif_codes \
                if notif_codes is not None else data.notif_daily
            await data.save()
        await ctx.respond(embed=await _check(ctx.author.id))

    @cmd.is_owner()
    @genshin_cmds.command()
    async def unlock(self, ctx: discord.ApplicationContext):
        await ctx.send_modal(system.UnlockModal(HoyoLabData))

    @cmd.is_owner()
    @genshin_cmds.command()
    async def lock(self, ctx: discord.ApplicationContext):
        HoyoLabData.clear_key()
        await ctx.respond(
            embed=system.make_embed('HoyoLabData Locked', ctx=ctx),
            ephemeral=True)

    @cmd.is_owner()
    @daily_rewards_cmds.command()
    async def induce_auto_redeem(self, ctx: discord.ApplicationContext):
        await ctx.respond('Triggering `auto_redeem-daily`.')
        await auto_redeem_daily(ctx.bot)


CHECKIN_ICON = db.get_json_data()['check-in icon']


def _make_client(data: HoyoLabData) -> genshin.Client:
    client = genshin.Client(game=genshin.Game.GENSHIN)
    client.set_cookies(data.cookies)
    return client


async def _get_client(snowflake: int) -> \
        genshin.Client | system.ErrorEmbed:
    if isinstance(data := await HoyoLabData.load(snowflake), HoyoLabData):
        return _make_client(data)
    return system.make_error(
        'Failed to Retrieve User Data',
        'Please configure your information using '
        '`/genshin configure cookies`.')


async def _redeem_daily(
        client: genshin.Client,
        ctx: discord.ApplicationContext = None) -> \
        discord.Embed:
    try:
        reward = await client.claim_daily_reward()
        embed = system.make_embed(
            'Daily Rewards Claimed',
            f'{reward.amount}x {reward.name}', ctx)
        embed.set_thumbnail(url=reward.icon)
        embed.set_author(name='HoyoLab Daily Check-In',
                         icon_url=CHECKIN_ICON)
        return embed
    except genshin.AlreadyClaimed:
        return system.make_error(
            'Daily Rewards Already Claimed',
            'Failed to claim daily rewards as '
            'they have already been claimed.')
    except genshin.InvalidCookies:
        return system.make_error(
            'Invalid Cookies',
            'Failed to claim daily rewards as saved cookies are invalid')


# @loop(time=dt.time(0, 5, 5, tzinfo=dt.timezone(dt.timedelta(hours=8))))
@loop(time=dt.time(16, 15, 5))
async def auto_redeem_daily(bot: cmd.Bot):
    logger.info('Automatically claiming daily rewards.')

    tasks = []  # Python 3.11: ToDo: asyncio.TaskGroup
    async for person in HoyoLabData.load_gen(auto_daily=True):
        client = _make_client(person)
        tasks.append(asyncio.create_task(system.do_and_dm(
            user_id=person.snowflake,
            bot=bot,
            coro=_redeem_daily(client),
            send=person.notif_daily)))
    for task in tasks:
        await task


async def _redeem_code(
        client: genshin.Client, code: str, tries: int = 0) \
        -> discord.Embed | system.ErrorEmbed:
    try:
        await client.redeem_code(code)
        return system.make_embed(
            'Successfully Redeemed Code',
            f'Successfully redeemed `{code}`.')
    except genshin.RedemptionInvalid as e:
        return system.make_error(
            'Failed to Redeem Code',
            f'Could not redeem `{code}`. {e.msg}')
    except genshin.RedemptionClaimed:
        return system.make_error(
            'Failed to Redeem Code',
            f'Code `{code}` claimed already.')
    except genshin.RedemptionCooldown:
        if tries < 3:
            await asyncio.sleep(tries + 1)
            return await _redeem_code(client, code, tries + 1)
        return system.make_error(
            'Failed to Redeem Code',
            f'Redemption on cooldown.\nCode: `{code}`')


async def _check(user_id: int,
                 ctx: discord.ApplicationContext = None, *,
                 color: discord.Color = None) \
        -> discord.Embed | system.ErrorEmbed:
    if not (client := await _get_client(user_id)):
        return system.make_error(
            'No Data Present',
            'Your HoyoLab cookies are not saved.')
    try:
        check = await client.get_partial_genshin_user(client.uid)
    except genshin.CookieException:
        return system.make_error(
            'Invalid Cookie Data',
            'Unable to login to HoyoLab with your cookies.')

    embed = system.make_embed(
        'Account Successfully Connected', '', ctx=ctx, color=color)
    embed.add_field(
        name='Connected Account',
        value=f'- `{check.info.nickname}` on '
              f'`{check.info.server.upper()}` servers.\n'
              f'- Level/AR `{check.info.level}`, '
              f'`{len(check.characters)}` Characters.\n',
        inline=False)

    for name, value in (await HoyoLabData.load(user_id)).settings.items():
        for option in HoyoLab.settings.options:
            if name == option.name:
                embed.add_field(
                    name=f'{name} (`{value}`)',
                    value=option.description,
                    inline=False)
                break

    return embed