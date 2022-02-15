"""Start up of the bot, run this file."""
import logging
import sys
from asyncio import sleep
from typing import Tuple

import discord
import discord.ext.commands as cmd
import yaml

from Cogs import cog_manager

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format='{asctime}|{levelname}|{name}\n\t{message}\n',
                    datefmt='%m/%d/%Y %H:%M:%S', style='{')

_guild_prefixes = {}
"""The prefixes for the guilds as a dict of [Guild ID, prefix]"""
DEFAULT_GUILD_PREFIX = '|'
"""The prefix that will be assigned if no prefix exists"""


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info('Loading Cog: System')
    bot.add_cog(System(bot))


def teardown(bot: cmd.Bot):
    """Removes the cog from the bot"""
    logger.info('Unloading Cog: System')
    bot.remove_cog(f'{System.qualified_name}')


def get_guild_prefix(bot: cmd.Bot, message: discord.Message) -> Tuple[str, str]:
    """
    Gets the prefix of a guild

    :param bot: The bot
    :param message: The message that may or may not have the prefix in it
    :return: The command prefix for the guild
    """
    logger.debug(f'Getting guild prefix for {message.guild.id} '
                 f'({message.guild.name})')
    # try:
    #     return _guild_prefixes[message.guild.id], bot.user.mention
    # except KeyError:
    #     logger.info(f'Guild {message.guild} ({message.guild.id}) '
    #                 f'not recognised, adding.')
    #     _guild_prefixes[message.guild.id] = DEFAULT_GUILD_PREFIX
    #     return _guild_prefixes[message.guild.id], bot.user.mention
    prefixes = bot.get_cog(System.__name__).prefixes
    if message.guild.id not in prefixes:
        logger.info(f'Guild {message.guild} ({message.guild.id}) '
                    f'not recognised, adding as {DEFAULT_GUILD_PREFIX}.')
        prefixes[message.guild.id] = DEFAULT_GUILD_PREFIX
    return prefixes[message.guild.id], bot.user.mention


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


class System(cog_manager.Cog):
    """Commands for bot settings and maintenance."""

    def __init__(self, bot: cmd.Bot):
        self.prefixes = {}
        super().__init__(bot)
        self._save_attrs.add('prefixes')

    @cmd.command()
    @cmd.guild_only()
    @cmd.has_permissions(manage_nicknames=True)
    async def change_prefix(self, ctx: cmd.Context, new_prefix: str):
        """Change the guild's prefix for the bot.

        :param ctx: The parameter given by Discord.
        :param new_prefix: The new prefix.
        """
        logger.info('')
        # change_guild_prefix(ctx.guild.id, new_prefix)
        self.prefixes[ctx.guild.id] = new_prefix
        await ctx.send(embed=discord.Embed(
            title='Command Prefix Changed',
            description=f'Prefix now set to: `{new_prefix}`',
            color=invert_color(ctx.me.color)))

    @cmd.command()
    @cmd.has_guild_permissions(manage_guild=True)
    async def disable(self, ctx: cmd.Context, command: str):
        """Disable (and re-enable) the specified command

        :param ctx: The parameter given by Discord
        :param command: The command name to disable or re-enable
        """
        if any([command == c.name for c in self.bot.commands]):
            com = self.bot.get_command(command)
            if isinstance(com.cog, cog_manager.Cog) and \
                    command in com.cog._disabled_commands:
                disabled = com.cog._disabled_commands
                if ctx.guild.id not in disabled[command]:
                    disabled[command].add(ctx.guild.id)
                    await self._send_embed(ctx, 'Disabled Command',
                                           f'{command} is now disabled.')
                else:
                    disabled[command].remove(ctx.guild.id)
                    await self._send_embed(ctx, 'Enabled Command',
                                           f'{command} is now re-enabled.')
            else:
                await self._send_error(ctx, desc=f'Cannot disable command {command}.')
        else:
            await self._send_error(ctx, desc=f'Unknown Command `{command}`.')

    @cmd.Cog.listener()
    async def on_ready(self):
        """Final Setup after Bot is fully connected to Discord"""
        logger.info(f'Logged in as {self.bot.user.id} ({self.bot.user}).')

    @cmd.Cog.listener()
    async def on_command(self, ctx: cmd.Context):
        """Logs attempted execution of a command."""
        logger.info(f'Command [{ctx.command.qualified_name}] invoked by'
                    f' {ctx.author.id} ({ctx.author.display_name})')

    @cmd.command(hidden=True, name='shutdown')
    @cmd.is_owner()
    async def shutdown_command(self, ctx: cmd.Context):
        """Does actions necessary to end execution of the bot."""
        logger.info('Shutting down.')
        cog_manager.call_shutdown(self.bot)
        await ctx.send(embed=discord.Embed(title='Shutting Down'))
        # cog_manager.save_guild_settings(self.bot)
        # saving.guild_prefixes_save(_guild_prefixes)
        while not cog_manager.shutdown_complete(self.bot):
            await sleep(.5)
        await self.bot.close()

    # @cmd.command(hidden=True)
    # @cmd.is_owner()
    # async def unload_cog(self, ctx: cmd.Context, cog_name: str):
    #     if cog_name not in self.bot.cogs:
    #         await self._send_error(ctx, 'Unknown Cog Name',
    #                                f'Bot does not have a Cog called {cog_name}')
    #         return
    #     if not cog_name == self.qualified_name:
    #         self.bot.remove_cog(cog_name)
    #     else:
    #         await self._send_error(ctx, 'Cannot Unload This Cog',
    #                                'This Cog can\'t be unloaded, '
    #                                'as that would probably not end well.')
    #
    # async def load_cog(self, ctx: cmd.Context, cog_name: str):
    #     if cog_name in self.bot.cogs:
    #         await self._send_error(ctx, 'Cog Already Loaded',
    #                                f'Cog {cog_name} has already been loaded.')

    @cmd.command(hidden=True)
    @cmd.is_owner()
    async def unload_extension(self, ctx: cmd.Context, name: str):
        if name == __file__[:__file__.find('.py')]:
            await self._send_error(ctx, f'Cannot Unload {name}',
                                   f'It is probably a bad idea to do this.'
                                   f'Try the `reload_extension` command instead')
        try:
            self.bot.unload_extension(name)
        except cmd.ExtensionError as e:
            # ToDo: Unload_Extension Error Description
            await self._send_error(ctx, title=e.name, desc=e.args[0])

    @cmd.command(hidden=True)
    @cmd.is_owner()
    async def load_extension(self, ctx: cmd.Context, name: str):
        try:
            self.bot.load_extension(name)
        except cmd.ExtensionError as e:
            # ToDo: Unload_Extension Error Description
            await self._send_error(ctx, title=e.name, desc=e.args[0])

    @cmd.command(hidden=True)
    @cmd.is_owner()
    async def reload_extension(self, ctx: cmd.Context, name: str):
        # if name not in self.bot.extensions and name in self.bot.cogs:
        #     name = self.bot.get_cog(name).
        try:
            self.bot.reload_extension(name)
        except cmd.ExtensionError as e:
            # ToDo: Unload_Extension Error Description
            await self._send_error(ctx, title=e.name, desc=e.args[0])

    @cmd.command(hidden=True, name='exec')
    @cmd.is_owner()
    async def execute(self, ctx: cmd.Context, *, request: str = ''):
        """Allows me to better fix the bot without restarting it."""
        try:
            command = request[request.index('```python\n') + len('```python\n'):
                              request.rindex('```')]
        except ValueError:
            await self._send_error(ctx, "Evaluation Error",
                                   "Could not find code block")
            return
        try:
            exec(command)
        except Exception as e:
            await self._send_error(ctx, str(e), command)
            return
        await ctx.send(embed=discord.Embed(title='Evaluation').add_field(
            name='Command', value=command))

    @cmd.command(hidden=True, name='eval')
    @cmd.is_owner()
    async def evaluate(self, ctx: cmd.Context, *, command: str = ''):
        """Allows me to better fix the bot without restarting it."""
        try:
            result = eval(command)
        except Exception as e:
            await self._send_error(ctx, str(e), command)
            return
        await ctx.send(embed=discord.Embed(title='Evaluation').add_field(
            name='Command', value=command).add_field(
            name='Result', value=result))


if __name__ == '__main__':
    # Callable function needs signature of (cmd.Bot, discord.Message)
    _bot = cmd.Bot(command_prefix=get_guild_prefix,
                   owner_id=612101930985979925)
    _bot.load_extension('main')
    cog_manager.load_extensions(_bot, ['vc_log', 'misc', 'dumb'])
    # _bot.help_command = cog_manager.HelpCommand()
    cog_manager.load_guild_settings(_bot)
    pass
    with open(r'saves/bot_key.json') as file:
        key = yaml.safe_load(file)
    _bot.run(key)
