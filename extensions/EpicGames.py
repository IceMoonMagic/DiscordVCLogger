import requests
import asyncio
import dataclasses as dc
import datetime as dt

import discord
import discord.ext.commands as cmd

import database as db
import system

logger = db.get_logger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info(f'Loading Cog: {__name__}')
    bot.add_cog(EpicGames(bot))


def teardown(bot: cmd.Bot):
    """Removes the cog from the bot"""
    logger.info('Unloading Cog: HoyoLab Cog')
    bot.remove_cog(EpicGames.qualified_name)


EPIC_FREE_PROMOTIONS_URL = \
    (r'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?'
     r'locale=en-US&country=US&allowCountries=US')


@dc.dataclass(frozen=True)
class FreeGame(db.Storable):
    primary_key_name = '_p_key'
    table_name = 'EpicGamesFreeGames'

    name: str
    start: dt.datetime
    end: dt.datetime
    price_str: str
    _p_key: int = dc.field(default=None)

    def __post_init__(self: db.S) -> db.S:
        if self._p_key is None:
            object.__setattr__(self, '_p_key', hash(self))
        return super().__post_init__()

    @property
    def active(self) -> bool:
        return self.start <= dt.datetime.now(tz=dt.timezone.utc) < self.end


@dc.dataclass
class FreeNotifications(db.Storable):
    primary_key_name = 'discord_snowflake'
    table_name = 'EpicGamesNotifications'

    discord_snowflake: int

    @property
    def snowflake(self) -> int:
        return self.discord_snowflake


class EpicGames(cmd.Cog):
    def __init__(self, bot: cmd.Bot):
        self.bot = bot
        self.check_loop: asyncio.Task | None = None

    @cmd.Cog.listener()
    async def on_ready(self):
        if self.check_loop is None:
            self.check_loop = asyncio.create_task(games_check_loop(self.bot))

    epic_cmds = discord.SlashCommandGroup('epic', 'epic games')

    @staticmethod
    def epic_check(ctx: discord.ApplicationContext) -> bool:
        to = ctx.channel
        print(type(to))
        if isinstance(to, discord.PartialMessageable):
            return True
        perms = to.permissions_for(ctx.author)
        if perms.manage_webhooks:
            return True
        elif isinstance(to, discord.abc.GuildChannel) and not perms.manage_channels:
            return True
        elif isinstance(to, discord.Thread) and not perms.manage_threads:
            return True
        return False

    @epic_cmds.command()
    @cmd.check(epic_check)
    @system.autogenerate_options
    async def add_notif(
            self,
            ctx: discord.ApplicationContext):

        await ctx.defer()
        if isinstance(to := ctx.channel, discord.PartialMessageable):
            to = ctx.author
        to_notif = FreeNotifications(to.id)
        await to_notif.save()
        await ctx.respond(embed=system.make_embed(
            title='Notifications Added',
            desc=f'Messages for free games on The Epic Games Store '
                 f'will now be sent here.'
        ))
        if self.check_loop is None or self.check_loop.done():
            self.check_loop = asyncio.create_task(games_check_loop(self.bot))
        else:
            await ctx.respond(embeds=await get_game_embeds(
                games=await FreeGame.load_all(),
                last_notif=dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
            ))

    @epic_cmds.command()
    @cmd.check(epic_check)
    @system.autogenerate_options
    async def rm_notif(
            self,
            ctx: discord.ApplicationContext):
        await ctx.defer()
        if isinstance(to := ctx.channel, discord.PartialMessageable):
            to = ctx.author
        await FreeNotifications.delete(to.id)
        await ctx.respond(embed=system.make_embed(
            title='Notifications Removed',
            desc=f'Messages for free games on The Epic Games Store '
                 f'will now not be sent here.'
        ))

    @epic_cmds.command()
    async def current(
            self,
            ctx: discord.ApplicationContext):
        await ctx.defer()
        if self.check_loop is None or self.check_loop.done():
            games, _ = await fetch_free_games()
        else:
            games = await FreeGame.load_all()
        await ctx.respond(embeds=await get_game_embeds(
            games=games,
            last_notif=dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
        ))


async def get_game_embeds(
        games: list[FreeGame],
        last_notif: dt.datetime
) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []
    for game in games:
        if game.start > last_notif and game.active:
            embeds.append(system.make_embed(
                title=f'`{game.name}` is Free on The Epic Games Store',
                desc=f'{system.get_time_str(game.start, "f")} - '
                     f'{system.get_time_str(game.end, "f")}'
                     f'({system.get_time_str(game.end, "R")})'
                     f'\nNormally: {game.price_str}'
            ))
    return embeds


async def games_check_loop(bot: cmd.Bot):
    last_update = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
    while len(notif := await FreeNotifications.load_all()) > 0:
        fetched_games, next_update = await fetch_free_games()
        await FreeGame.delete_all()
        for game in fetched_games:
            await game.save()
        async with asyncio.TaskGroup() as tg:
            embeds = await get_game_embeds(fetched_games, last_update)
            for n in notif:
                if (channel := bot.get_channel(n.snowflake)) is None:
                    channel = await system.get_dm(n.snowflake, bot)
                tg.create_task(channel.send(embeds=embeds))
        last_update = dt.datetime.now(tz=dt.timezone.utc)
        sleep = next_update - last_update
        await asyncio.sleep(sleep.total_seconds())


async def fetch_free_games() -> tuple[list[FreeGame], dt.datetime]:
    response = await asyncio.get_running_loop().run_in_executor(
        None,
        requests.get,
        EPIC_FREE_PROMOTIONS_URL)
    games_raw = response.json()['data']['Catalog']['searchStore']['elements']
    games_raw = [game for game in games_raw if game['promotions'] is not None]

    next_update = dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(days=7)
    games: list[FreeGame] = []
    for game in games_raw:
        if len(promotions := game['promotions']['promotionalOffers']) == 0:
            promotions = game['promotions']['upcomingPromotionalOffers']
        start = dt.datetime.fromisoformat(
            promotions[0]['promotionalOffers'][0]['startDate'])
        end = dt.datetime.fromisoformat(
            promotions[0]['promotionalOffers'][0]['endDate'])
        games.append(FreeGame(
            name=game['title'],
            start=start,
            end=end,
            price_str=game['price']['totalPrice']['fmtPrice']['originalPrice']
        ))
        next_update = min(next_update, end if games[-1].active else start)

    return games, next_update
