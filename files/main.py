"""Start up of the bot, run this file."""
import logging
import sys
from asyncio import sleep

import discord
import discord.ext.commands as cmd
from typing import Tuple
import saving
from Cogs import cog_manager

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format='{asctime}|{levelname}|{name}\n\t{message}\n',
                    datefmt='%m/%d/%Y %H:%M:%S', style='{')

_guild_prefixes = saving.guild_prefixes_load()
"""The prefixes for the guilds as a dict of [Guild ID, prefix]"""
DEFAULT_GUILD_PREFIX = '|'
"""The prefix that will be assigned if no prefix exists"""


def get_guild_prefix(bot: cmd.Bot, message: discord.Message) -> Tuple[str, str]:
    """
    Gets the prefix of a guild

    :param bot: The bot
    :param message: The message that may or may not have the prefix in it
    :return: The command prefix for the guild
    """
    logger.debug(f'Getting guild prefix for {message.guild.id} '
                 f'({message.guild.name})')
    try:
        return _guild_prefixes[message.guild.id], bot.user.mention
    except KeyError:
        logger.info(f'Guild {message.guild} ({message.guild.id}) '
                    f'not recognised, adding.')
        _guild_prefixes[message.guild.id] = DEFAULT_GUILD_PREFIX
        return _guild_prefixes[message.guild.id], bot.user.mention


def invert_color(color: discord.Color) -> discord.Color:
    return discord.Color.from_rgb(255 - color.r, 255 - color.g, 255 - color.b)


def change_guild_prefix(guild_id: int, new_prefix: str) -> None:
    """
    Changes the registered prefix of a guild

    :param guild_id: The ID of the guild getting a new prefix
    :param new_prefix: The new prefix for the guild
    :return: None
    """
    _guild_prefixes[guild_id] = new_prefix


class System(cmd.Cog):
    """Commands for bot settings and maintenance."""

    def __init__(self, bot: cmd.Bot):
        self.bot = bot

    @cmd.command()
    @cmd.guild_only()
    @cmd.has_permissions(manage_nicknames=True)
    async def change_prefix(self, ctx: cmd.Context, new_prefix: str):
        """Change the guild's prefix for the bot.

        :param ctx: The parameter given by Discord.
        :param new_prefix: The new prefix.
        """
        logger.info('')
        change_guild_prefix(ctx.guild.id, new_prefix)
        await ctx.send(embed=discord.Embed(
            title='Command Prefix Changed',
            description=f'Prefix now set to: `{new_prefix}`',
            color=invert_color(ctx.me.color)))

    @cmd.Cog.listener()
    async def on_ready(self):
        """Final Setup after Bot is fully connected to Discord"""
        logger.info(f'Logged in as {self.bot.user.id} ({self.bot.user}).')

    @cmd.Cog.listener()
    async def on_command(self, ctx: cmd.Context):
        """Logs attempted execution of a command."""
        logger.info(f'Command [{ctx.command.qualified_name}] invoked by'
                    f' {ctx.author.id} ({ctx.author.display_name})')

    @cmd.command(hidden=True)
    @cmd.is_owner()
    async def shutdown(self, ctx: cmd.Context):
        """Does actions necessary to end execution of the bot."""
        logger.info('Shutting down.')
        cog_manager.call_shutdown(self.bot)
        await ctx.send(embed=discord.Embed(title='Shutting Down'))
        saving.guild_prefixes_save(_guild_prefixes)
        while not cog_manager.shutdown_complete(self.bot):
            await sleep(.5)
        await self.bot.close()

    @cmd.command(hidden=True, name='eval')
    @cmd.is_owner()
    async def evaluate(self, ctx: cmd.Context, *, command: str = ''):
        """Allows me to better fix the bot without restarting it."""
        logger.info('Evaluate')
        try:
            result = eval(command)
        except Exception as e:
            await self.bot.error(ctx, str(e), command)
            return
        await ctx.send(embed=discord.Embed(title='Evaluation').add_field(
            name='Command', value=command, inline=False).add_field(
            name='Result', value=result))


if __name__ == '__main__':
    # Callable function needs signature of (cmd.Bot, discord.Message)
    _bot = cmd.Bot(command_prefix=get_guild_prefix,
                   owner_id=612101930985979925)
    cog_manager.add_cogs(_bot, ['error', System, 'vc_log', 'Misc'])
    _bot.run(saving.bot_key_load())
