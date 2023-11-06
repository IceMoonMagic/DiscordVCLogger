import asyncio
import dataclasses as dc
import datetime as dt

import discord
import discord.ext.commands as cmd
import requests

import database as db
import utils

logger = db.get_logger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info(f"Loading Cog: {__name__}")
    bot.add_cog(EpicGames(bot))


def teardown(bot: cmd.Bot):
    """Removes the cog from the bot"""
    logger.info("Unloading Cog: HoyoLab Cog")
    bot.remove_cog(EpicGames.qualified_name)


epic_json = db.get_json_data(__name__)
EPIC_FREE_PROMOTIONS_URL = epic_json.get("promotions url", "")
EPIC_STORE_HOME = epic_json.get("store url", "")
EPIC_ICON = epic_json.get("store icon", "")
del epic_json


@dc.dataclass(frozen=True)
class FreeGame(db.Storable):
    primary_key_name = "_p_key"
    table_name = "EpicGamesFreeGames"

    name: str
    desc: str
    page_url: str
    start: dt.datetime
    end: dt.datetime
    price_str: str
    image_url: str
    _p_key: int = dc.field(default=None)

    def __post_init__(self: db.S) -> db.S:
        if self._p_key is None:
            object.__setattr__(self, "_p_key", hash(self))
        return super().__post_init__()

    @property
    def active(self) -> bool:
        return self.start <= dt.datetime.now(tz=dt.timezone.utc) < self.end

    def embed(self) -> discord.Embed:
        if self.page_url:
            url = f"{EPIC_STORE_HOME}/p/{self.page_url}"
        else:
            url = None
        image = self.image_url or None
        return (
            utils.make_embed(
                title=f"`{self.name}`",
                desc=self.desc,
                url=url,
            )
            .set_author(
                name="Free on the Epic Games Store",
                url=EPIC_STORE_HOME,
                icon_url=EPIC_ICON,
            )
            .set_image(url=image)
            .add_field(name="Normally", value=self.price_str, inline=True)
            .add_field(
                name="Start Time",
                value=f'{utils.format_dt(self.start, "f")}\n'
                f'({utils.format_dt(self.start, "R")})',
                inline=True,
            )
            .add_field(
                name="End Time",
                value=f'{utils.format_dt(self.end, "f")}\n'
                f'({utils.format_dt(self.end, "R")})',
                inline=True,
            )
        )


@dc.dataclass
class FreeNotifications(db.Storable):
    primary_key_name = "discord_snowflake"
    table_name = "EpicGamesNotifications"

    discord_snowflake: int
    last_update: dt.datetime = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)

    @property
    def snowflake(self) -> int:
        return self.discord_snowflake

    async def send_games(self, bot: cmd.Bot, games: list[FreeGame]):
        if (channel := bot.get_channel(self.snowflake)) is None:
            channel = await utils.get_dm(self.snowflake, bot)
        embeds = []
        for game in games:
            if game.active and game.start > self.last_update:
                embeds.append(game.embed())
        self.last_update = utils.utcnow()
        if len(embeds) > 0:
            try:
                if isinstance(channel, discord.Thread) and channel.me is None:
                    await channel.join()
                await channel.send(embeds=embeds)
            except (discord.HTTPException, discord.Forbidden) as e:
                pass
        await self.save()


class EpicGames(cmd.Cog):
    def __init__(self, bot: cmd.Bot):
        self.bot = bot
        self.check_loop: asyncio.Task | None = None

    @cmd.Cog.listener()
    async def on_ready(self):
        if self.check_loop is None:
            self.check_loop = asyncio.create_task(games_check_loop(self.bot))

    epic_cmds = discord.SlashCommandGroup("epic", "epic games")

    @staticmethod
    def epic_check(ctx: discord.ApplicationContext) -> bool:
        to = ctx.channel
        print(type(to))
        if isinstance(to, discord.PartialMessageable):
            return True
        perms = to.permissions_for(ctx.author)
        if perms.manage_webhooks:
            return True
        elif (
            isinstance(to, discord.abc.GuildChannel)
            and not perms.manage_channels
        ):
            return True
        elif isinstance(to, discord.Thread) and not perms.manage_threads:
            return True
        return False

    @epic_cmds.command()
    @cmd.check(epic_check)
    @utils.autogenerate_options
    async def add_notif(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        if isinstance(to := ctx.channel, discord.PartialMessageable):
            to = ctx.author
        to_notif = FreeNotifications(to.id)
        await to_notif.save()
        await ctx.respond(
            embed=utils.make_embed(
                title="Notifications Added",
                desc=f"Messages for free games on The Epic Games Store "
                f"will now be sent here.",
            )
        )
        if self.check_loop is None or self.check_loop.done():
            self.check_loop = asyncio.create_task(games_check_loop(self.bot))
        else:
            await to_notif.send_games(
                bot=ctx.bot, games=await FreeGame.load_all()
            )

    @epic_cmds.command()
    @cmd.check(epic_check)
    @utils.autogenerate_options
    async def rm_notif(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        if isinstance(to := ctx.channel, discord.PartialMessageable):
            to = ctx.author
        await FreeNotifications.delete(to.id)
        await ctx.respond(
            embed=utils.make_embed(
                title="Notifications Removed",
                desc=f"Messages for free games on The Epic Games Store "
                f"will now not be sent here.",
            )
        )

    @epic_cmds.command()
    async def current(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        if self.check_loop is None or self.check_loop.done():
            games, _ = await fetch_free_games()
        else:
            games = await FreeGame.load_all()
        await ctx.respond(embeds=[g.embed() for g in games if g.active])

    @cmd.is_owner()
    @epic_cmds.command()
    async def hard_reset(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        if not (self.check_loop is None) and not self.check_loop.done():
            self.check_loop.cancel()
            self.check_loop = asyncio.create_task(games_check_loop(self.bot))
        await ctx.respond(
            embed=utils.make_embed(
                "Hard Reset Free Games",
                "The game_check_loop has been replaced "
                "and free games re-fetched.",
            )
        )


async def games_check_loop(bot: cmd.Bot):
    while len(notif := await FreeNotifications.load_all()) > 0:
        fetched_games, next_update = await fetch_free_games()
        await FreeGame.delete_all()
        for game in fetched_games:
            await game.save()
        async with asyncio.TaskGroup() as tg:
            for n in notif:
                tg.create_task(n.send_games(bot, fetched_games))
        sleep = next_update - utils.utcnow()
        await asyncio.sleep(sleep.total_seconds())


async def fetch_free_games() -> tuple[list[FreeGame], dt.datetime]:
    response = await asyncio.get_running_loop().run_in_executor(
        None, requests.get, EPIC_FREE_PROMOTIONS_URL
    )
    games_raw = response.json()["data"]["Catalog"]["searchStore"]["elements"]
    games_raw = [game for game in games_raw if game["promotions"] is not None]

    next_update = dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(days=7)
    games: list[FreeGame] = []
    for game in games_raw:
        promotions = []
        if len(game["promotions"]["promotionalOffers"]) != 0:
            promotions += game["promotions"]["promotionalOffers"][0][
                "promotionalOffers"
            ]
        if len(game["promotions"]["upcomingPromotionalOffers"]) != 0:
            promotions += game["promotions"]["upcomingPromotionalOffers"][0][
                "promotionalOffers"
            ]
        for promotion in promotions:
            if promotion["discountSetting"]["discountPercentage"] != 0:
                continue

            start = dt.datetime.fromisoformat(promotion["startDate"])
            end = dt.datetime.fromisoformat(promotion["endDate"])

            for img in game["keyImages"]:
                if img["type"] == "OfferImageWide":
                    image_url = img["url"]
                    break
            else:
                image_url = ""

            if (page_url := game["productSlug"]) is None:
                for offerMapping in game.get("offerMappings", []):
                    if page_url := offerMapping.get("pageSlug", False):
                        break
                else:
                    page_url = ""

            games.append(
                FreeGame(
                    name=game["title"],
                    desc=game["description"],
                    start=start,
                    end=end,
                    price_str=game["price"]["totalPrice"]["fmtPrice"][
                        "originalPrice"
                    ],
                    image_url=image_url,
                    page_url=page_url,
                )
            )
            next_update = min(next_update, end if games[-1].active else start)

    return games, next_update
