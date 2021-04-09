"""Functions to help managing Cogs."""
import discord.ext.commands as cmd
import logging
from typing import Union, List


def add_cogs(bot: cmd.Bot, cogs: List[Union[str, cmd.cog.CogMeta]]):
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


def call_shutdown(bot: cmd.Bot):
    """Sends signals to the Cogs to start shutting down."""
    for cog_name in bot.cogs:  # ToDo: get actual cog, not just name
        cog = bot.get_cog(cog_name)
        if hasattr(cog, 'shutdown'):
            if callable(cog.shutdown):
                cog.shutdown()
            elif isinstance(cog.shutdown, (bool, type(None))):
                cog.shutdown = True


def shutdown_complete(bot: cmd.Bot) -> bool:
    """Determines if all Cogs are done shutting down."""
    # complete = True
    for cog_name in bot.cogs:
        cog = bot.get_cog(cog_name)
        if hasattr(cog, 'shutdown_complete'):
            if callable(cog.shutdown_complete):
                if not cog.shutdown_complete():
                    return False
            elif isinstance(cog.shutdown_complete, bool):
                if not cog.shutdown_complete:
                    return False
    return True
