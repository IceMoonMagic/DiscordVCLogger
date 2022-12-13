"""Functions to help managing Cogs."""

import re
from datetime import datetime

import discord
import discord.ext.commands as cmd
from discord import ApplicationContext

import database as db

logger = db.get_logger(__name__)


def load_extensions(bot: cmd.Bot, cogs: list[str | cmd.Cog]):
    for cog in cogs:
        if isinstance(cog, str):
            bot.load_extension(f'Cogs.{cog}')
        elif issubclass(cog, cmd.Cog):
            bot.add_cog(cog(bot))
        else:
            raise ValueError(f'cogs elements must be str or a subclass of '
                             f'discord.ext.commands.Cog, got {type(cog)}')


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

    # @cmd.Cog.listener()
    async def cog_command_error(self,
                                ctx: ApplicationContext,
                                error: discord.ApplicationCommandError):
        """Catches when a command throws an error."""
        if isinstance(error, cmd.CommandNotFound):
            return
        raise_it = False
        logger.warning(
            f'Command Error: {ctx.command.qualified_name}'
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
            for permission in error.missing_permissions:
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

        await ctx.respond(embed=self._make_error(ctx, title, desc))

        if raise_it:
            raise error

    @staticmethod
    def _make_error(
            ctx: ApplicationContext, title: str = 'Error',
            desc: str = 'Generic Error'):
        """Creates a uniform error embed for other methods to send."""
        embed = discord.Embed(title=title, description=desc,
                              color=discord.Color.dark_red())
        embed = embed.add_field(
            name='Command', value=ctx.command.qualified_name).add_field(
            name='Member', value=ctx.author.mention)
        # ).set_footer(
        #     text=f'Try {ctx.prefix}help or {ctx.prefix}help [command] '
        #          'for more information.')
        return embed

    @staticmethod
    def _make_embed(
            ctx: ApplicationContext, title: str, desc: str,
            color: discord.Color = None):
        """Creates a uniform standard embed for other methods to send."""
        if color is None:
            color = ctx.me.color
        return ctx.send(embed=discord.Embed(
            title=title, description=desc, color=color))

    @staticmethod
    def _regex_args(string: str, expected: set,
                    error_unknown: bool = True) -> dict:
        tokens = [i for i in re.split("(\s|\".*?\"|'.*?')", string) if
                  i.strip()]
        args = {None: {'raw': tokens, 'unexpected': {}}}
        for t in range(len(tokens)):
            if tokens[t] is not None and tokens[t] not in expected:
                if error_unknown:
                    raise cmd.ArgumentParsingError(
                        f'Unexpected Argument {tokens[t]}')
                args[None]['unexpected'][t] = tokens[t]
            if t != len(tokens) - 1:
                args[tokens[t]] = tokens[t + 1]
                tokens[t] = tokens[t + 1] = None
        return args


def get_time_str(time: datetime | int,
                 time_format: str = '') -> str:
    if time_format not in {'', 't', 'T', 'd', 'D', 'f', 'F', 'R'}:
        raise ValueError(f'Unrecognized time format {time_format}')
    if isinstance(time, datetime):
        time = int(time.timestamp())
    return f'<t:{time}:{time_format}>'
