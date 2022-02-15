"""Functions to help managing Cogs."""
import logging
import re
from typing import Union, List

import discord
import discord.ext.commands as cmd
import yaml

logger = logging.getLogger(__name__)


def file_path(filename: str) -> str:
    return f'saves/{filename}.yaml'


def save_guild_settings(bot: cmd.Bot):
    # out = {guild_id: {'prefix': prefixes[guild_id]} for guild_id in prefixes}
    out = {}
    for cog_name in bot.cogs:
        cog = bot.get_cog(cog_name)
        if not isinstance(cog, Cog):
            continue
        out[cog_name] = cog.save_settings()
    with open(r'saves/guild_settings.yaml', 'w') as save_file:
        save_file.seek(0)
        save_file.truncate()
        yaml.safe_dump(out, save_file)


def load_guild_settings(bot: cmd.Bot):
    with open(r'saves/guild_settings.yaml') as save_file:
        data = yaml.safe_load(save_file)
    for cog_name in data:
        cog = bot.get_cog(cog_name)
        if cog is not None and isinstance(cog, Cog):
            cog.load_settings(data[cog_name])


def load_extensions(bot: cmd.Bot, cogs: List[Union[str, cmd.cog.CogMeta]]):
    for cog in cogs:
        if isinstance(cog, str):
            bot.load_extension(f'Cogs.{cog}')
        elif issubclass(cog, cmd.Cog):
            bot.add_cog(cog(bot))
        else:
            raise ValueError(f'cogs elements must be str or a subclass of '
                             f'discord.ext.commands.Cog, got {type(cog)}')

    #     _bot.add_cog(_System(_bot))
    # for cog in reversed(['vc_log', 'Misc', 'error']):
    #     _bot.load_extension(f'Cogs.{cog}')


def call_shutdown(bot: cmd.Bot) -> dict:
    """Sends signals to the Cogs to start shutting down."""
    saved_settings = {}
    for cog_name in bot.cogs:
        cog = bot.get_cog(cog_name)
        if isinstance(cog, Cog):
            saved_settings[cog_name] = cog.save_settings()
            cog.shutdown()
    return saved_settings


def shutdown_complete(bot: cmd.Bot) -> bool:
    """Determines if all Cogs are done shutting down."""
    # complete = True
    for cog_name in bot.cogs.copy():
        cog = bot.get_cog(cog_name)
        if isinstance(cog, Cog):
            if not cog.shutdown_complete():
                return False
            else:
                bot.remove_cog(cog_name)
    return True


class Cog(cmd.Cog):

    def __new__(cls, *args, **kwargs):
        if cls is Cog:
            raise TypeError('Cog must be inherited to be instantiated.')
        return super().__new__(cls, args, kwargs)

    def __init__(self, bot: cmd.Bot, error_color: discord.Color = None):
        self.bot = bot
        if error_color is None:
            self.error_color = discord.Color.dark_red()
        else:
            self.error_color = error_color
        self._save_attrs = {'_disabled_commands'}
        self._disabled_commands = {}  # {com.name: {} for com in self.get_commands()}
        for command in self.get_commands():
            if not command.hidden:
                self._disabled_commands[command.name] = set()
        try:
            self.load_file()
        except FileNotFoundError:
            pass

    def shutdown(self) -> None:
        pass

    def shutdown_complete(self) -> bool:
        return True

    def save_settings(self, guild_id: int = None) -> dict:
        if guild_id is None:
            # return {'_disabled_commands': self._disabled_commands}
            return {name: self.__dict__[name] for name in self._save_attrs}

    def load_settings(self, settings: dict, guild_id: int = None) -> None:
        for attr in settings:
            if not hasattr(self, attr):
                raise AttributeError(f'Unknown Attribute: {attr} for {type(self)}')
            if isinstance(self.__getattribute__(attr), dict):
                self.__getattribute__(attr).update(settings[attr])
            else:
                setattr(self, attr, settings[attr])

    def save_file(self, filename: str = None):
        if filename is None:
            filename = self.qualified_name
        with open(file_path(filename), 'w') as file:
            file.seek(0)
            file.truncate()
            yaml.safe_dump(self.save_settings(), file)

    def load_file(self, filename: str = None):
        if filename is None:
            filename = self.qualified_name
        with open(file_path(filename), 'r') as file:
            self.load_settings(yaml.safe_load(file))

    def cog_unload(self):
        self.save_file()
        super().cog_unload()

    def cog_check(self, ctx):
        if ctx.command.qualified_name not in self._disabled_commands or \
                ctx.guild is None:
            return True
        if ctx.guild.id not in \
                self._disabled_commands[ctx.command.qualified_name]:
            return True
        raise cmd.DisabledCommand()

    async def cog_command_error(self, ctx: cmd.Context,
                                error: cmd.CommandError):
        """Catches when a command throws an error."""
        if isinstance(error, cmd.CommandNotFound):
            return
        elif isinstance(error, cmd.DisabledCommand):
            await self._send_error(ctx, 'Command is Disabled',
                                   f'Command `{ctx.command.qualified_name}` is '
                                   f'disabled and therefore cannot be used.')
            return
        raise_it = False
        logger.info(f'Command Error: {ctx.command.qualified_name}'
                    f' invoked by {ctx.author.id} ({ctx.author.display_name})'
                    f' which raised a(n) {type(error)}.')
        # ToDo: Look into more
        if isinstance(error, cmd.MissingRequiredArgument):
            expected = len(ctx.command.clean_params)
            given = expected - len(error.args)
            title = 'Missing or Invalid Arguments'
            desc = f'Expected: {expected}, Received: {given}'

        elif isinstance(error, (cmd.UnexpectedQuoteError,
                                cmd.ExpectedClosingQuoteError,
                                cmd.InvalidEndOfQuotedStringError)):
            title = 'Quote Error'
            desc = 'Due to the way arguments are handled, ' \
                   'the " (Double Quote) has the following limitations:\n' \
                   ' - Cannot be used as an argument itself\n' \
                   ' - Must always be used in pairs\n' \
                   ' - Must have a space after closing\n' \
                   'Also, note that anything within quotes will count ' \
                   'as a single argument rather than separated by spaces.'

        elif isinstance(error,
                        (cmd.MissingPermissions, cmd.BotMissingPermissions)):
            title, desc = 'Missing Permissions', ''
            if isinstance(error, cmd.BotMissingPermissions):
                title = f'Bot {title}'
            first = True
            for permission in error.missing_perms:
                if not first:
                    desc += '\n'
                first = False
                desc += f' - {permission}'

        elif isinstance(error, cmd.NotOwner):
            title = 'Not Owner'
            desc = f'Only <@{self.bot.owner_id}> can use this command.'

        else:
            title = 'Unexpected Command Error'
            desc = 'If this issue persists, please inform ' \
                   f'<@{self.bot.owner_id}>'
            raise_it = True

        await self._send_error(ctx, title, desc)

        if raise_it:
            raise error

    async def _send_error(self, ctx: cmd.Context,
                          title: str = 'Error', desc: str = 'Generic Error'):
        """Creates a uniform error embed for other methods to send."""
        await ctx.send(embed=self.__add_error_footer(ctx, discord.Embed(
            title=title, description=desc, color=self.error_color)))

    @staticmethod
    async def _send_embed(ctx: cmd.Context, title: str, desc: str,
                          color: discord.Color = None):
        """Creates a uniform standard embed for other methods to send."""
        if color is None:
            color = ctx.me.color
        await ctx.send(embed=discord.Embed(
            title=title, description=desc, color=color))

    @staticmethod
    def __add_error_footer(ctx: cmd.Context,
                           embed: discord.Embed) -> discord.Embed:
        """Adds adds some informative information to error reports."""
        return embed.add_field(
            name='Command', value=ctx.command.qualified_name).add_field(
            name='Member', value=ctx.author.mention).add_field(
            name='Message', value=f'[Jump]({ctx.message.jump_url})'
        ).set_footer(
            text=f'Try {ctx.prefix}help or {ctx.prefix}help [command] '
                 'for more information.')

    @staticmethod
    def _regex_args(string: str, expected: set, error_unknown: bool = True) -> dict:
        tokens = [i for i in re.split("(\s|\".*?\"|'.*?')", string) if i.strip()]
        args = {None: {'raw': tokens, 'unexpected': {}}}
        for t in range(len(tokens)):
            if tokens[t] is not None and tokens[t] not in expected:
                if error_unknown:
                    raise cmd.ArgumentParsingError(f'Unexpected Argument {tokens[t]}')
                args[None]['unexpected'][t] = tokens[t]
            if t != len(tokens) - 1:
                args[tokens[t]] = tokens[t + 1]
                tokens[t] = tokens[t + 1] = None
        return args


# class HelpCommand(cmd.DefaultHelpCommand):
#
#     async def send_bot_help(self, mapping):
#         ctx = self.context
#         text = {}
#         for command in ctx.bot.commands:
#             if command.hidden:
#                 continue
#             if command.cog_name not in text:
#                 text[command.cog_name] = ''
#             help_str = command.help.split("\n")[0]
#             text[command.cog_name] += f'\n{command.name}\t-\t{help_str}'
#
#         unsorted = text[None]
#         del text[None]
#
#         embed = discord.Embed(color=ctx.me.color)
#         for key in sorted(list(text), key=str.casefold):
#             embed.add_field(name=key, value=text[key], inline=False)
#         embed.add_field(name='Misc', value=unsorted, inline=False)
#         await self.get_destination().send(embed=embed)
#
#     async def send_cog_help(self, cog):
#         ctx = self.context
#
#         embed = discord.Embed(title=f'{cog.qualified_name} Help',
#                               description=cog.description,
#                               color=ctx.me.color)
#         for command in cog.get_commands():
#             if not command.hidden:
#                 embed.add_field(name=command.name,
#                                 value=command.help,
#                                 inline=False)
#         await self.get_destination().send(embed=embed)
#
#     # async def send_group_help(self, group):
#     #     pass
#
#     async def send_command_help(self, command):
#         pass
#
#     # async def send_error_message(self, error):
#     #     pass
