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
    primary_key_name = 'name'
    table_name = 'EpicGamesFreeGames'

    name: str
    start: dt.datetime
    end: dt.datetime
    price_str: str

    @property
    def active(self) -> bool:
        return self.start <= dt.datetime.now(tz=dt.timezone.utc) < self.end


@dc.dataclass
class FreeNotifications(db.Storable):
    primary_key_name = 'discord_snowflake'
    table_name = 'EpicGamesNotifications'

    discord_snowflake: int
    channel_type: type

    @property
    def snowflake(self) -> int:
        return self.discord_snowflake


class EpicGames(cmd.Cog):
    pass


async def _games_notify(
        bot: cmd.Bot,
        send_to: list[FreeNotifications],
        games: list[FreeGame],
        last_notif: dt.datetime
):
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
    with asyncio.TaskGroup() as tg:
        for s in send_to:
            channel = bot.get_channel(s.snowflake)
            tg.create_task(channel.send(embeds=embeds))


async def games_check_loop(bot: cmd.Bot):
    last_update = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
    while len(notif := await FreeNotifications.load_all()) > 0:
        fetched_games, next_update = await fetch_free_games()
        await FreeGame.delete_all()
        async with asyncio.TaskGroup() as tg:
            for game in fetched_games:
                tg.create_task(game.save())
            tg.create_task(
                _games_notify(bot, notif, fetched_games, last_update))
            last_update = dt.datetime.now(tz=dt.timezone.utc)
            sleep = next_update - last_update
            tg.create_task(asyncio.sleep(sleep.total_seconds()))


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
