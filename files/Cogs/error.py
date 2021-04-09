"""Cog for Error Handling"""
import logging

import discord
import discord.ext.commands as cmd

logger = logging.getLogger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info('Loading Cog: Error Handler')
    bot.add_cog(ErrorHandler(bot, discord.Color.dark_red()))


class ErrorHandler(cmd.Cog):
    """Adds the cog to the bot"""

    def __init__(self, bot: cmd.Bot, error_color: discord.Color = None):
        self.bot = bot
        if not hasattr(bot, 'error'):
            self.bot.error = self.create_error
        if hasattr(bot, 'error_color'):
            self.error_color = bot.error_color
        else:
            if error_color is None:
                self.error_color = discord.Color.dark_red()
            else:
                self.error_color = error_color
            self.bot.error_color = self.error_color

    @cmd.Cog.listener()
    async def on_command_error(self, ctx: cmd.Context,
                               error: cmd.CommandError):
        """Catches when a command throws an error."""
        raise_it = False
        if isinstance(error, cmd.CommandNotFound):
            return
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

        await self.create_error(ctx, title, desc)

        if raise_it:
            raise error

    @staticmethod
    def add_error_footer(ctx: cmd.Context,
                         embed: discord.Embed) -> discord.Embed:
        """Adds adds some informative information to error reports."""
        return embed.add_field(
            name='Command', value=ctx.command.qualified_name).add_field(
            name='Member', value=ctx.author.mention).add_field(
            name='Message', value=f'[Jump]({ctx.message.jump_url})'
        ).set_footer(
            text=f'Try {ctx.prefix}help or {ctx.prefix}help [command] '
                 'for more information.')

    async def create_error(self, ctx: cmd.Context, title: str = 'Error',
                           desc: str = 'Generic Error'):
        """Creates a uniform error embed for other methods to send."""
        await ctx.send(embed=self.add_error_footer(ctx, discord.Embed(
            title=title, description=desc, color=self.error_color)))
