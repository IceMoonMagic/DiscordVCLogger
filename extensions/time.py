import asyncio
import dataclasses as dc
import datetime as dt

import discord
import discord.ext.commands as cmds

import database as db
import utils

logger = db.get_logger(__name__)


def setup(bot: cmds.Bot):
    """Adds the cog to the bot"""
    logger.info(f"Loading Cog: Time")
    bot.add_cog(TimeCommands())


def teardown(bot: cmds.Bot):
    """Removes the cog from the bot"""
    logger.info(f"Unloading Cog: Time")
    bot.remove_cog(f"{TimeCommands.qualified_name}")


class TimeCommands(cmds.Cog):

    formats = [
        ("Short Time", "t"),
        ("Long Time", "T"),
        ("Short Date", "d"),
        ("Long Date", "D"),
        ("Short Date/Time", "f"),
        ("Long Date/Time", "F"),
        ("Relative Time", "R"),
    ]
    time_cmds = discord.SlashCommandGroup("time", "foo")

    def make_timestamp_embed(
        self,
        ctx: discord.ApplicationContext,
        datetime: dt.datetime,
    ) -> discord.Embed:
        embed = utils.make_embed(
            f"Timestamps for `{int(datetime.timestamp())}`", ctx=ctx
        )
        for name, key in self.formats:
            string = utils.format_dt(datetime, key)
            embed.add_field(name=name, value=f"{string}\n`{string}`")
        return embed

    @time_cmds.command()
    # @utils.autogenerate_options
    async def now(
        self,
        ctx: discord.ApplicationContext,
    ):
        """
        Shows the current time as Discord Timestamps
        """
        # await ctx.defer()
        await ctx.respond(
            embed=self.make_timestamp_embed(
                ctx=ctx,
                datetime=utils.utcnow(),
            )
        )

    @time_cmds.command(name="in")
    @utils.autogenerate_options
    async def _in(
        self,
        ctx: discord.ApplicationContext,
        days: discord.Option(int) = 0,
        hours: discord.Option(int) = 0,
        minutes: discord.Option(int) = 0,
        seconds: discord.Option(int) = 0,
        milliseconds: discord.Option(int) = 0,
        microseconds: discord.Option(int) = 0,
    ):
        """
        Shows the time after specified delta as Discord Timestamps
        """
        # await ctx.defer()
        await ctx.respond(
            embed=self.make_timestamp_embed(
                ctx=ctx,
                datetime=utils.utcnow()
                + dt.timedelta(
                    # weeks=0,
                    days=days,
                    hours=hours,
                    minutes=minutes,
                    seconds=seconds,
                    milliseconds=milliseconds,
                    microseconds=microseconds,
                ),
            ),
        )

    @time_cmds.command()
    @utils.autogenerate_options
    async def at(
        self,
        ctx: discord.ApplicationContext,
        year: discord.Option(int, min_value=dt.MINYEAR, max_value=dt.MAXYEAR),
        month: discord.Option(int, min_value=1, max_value=12),
        day: discord.Option(int, min_value=1, max_value=31),
        hour: discord.Option(int, min_value=0, max_value=23) = 0,
        minute: discord.Option(int, min_value=0, max_value=59) = 0,
        second: discord.Option(int, min_value=0, max_value=59) = 0,
        microsecond: discord.Option(int, min_value=0, max_value=999999) = 0,
        tz_offset: discord.Option(int, min_value=-24, max_value=24) = 0,
    ):
        """
        Shows the specificed time as Discord Timestamps
        """
        # await ctx.defer()
        await ctx.respond(
            embed=self.make_timestamp_embed(
                ctx=ctx,
                datetime=dt.datetime(
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                    second=second,
                    microsecond=microsecond,
                    tzinfo=dt.timezone(dt.timedelta(hours=tz_offset)),
                ),
            ),
        )
