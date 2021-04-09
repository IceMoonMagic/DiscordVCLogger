"""Starts the bot on a user token"""
import json

import discord.ext.commands as cmd

from Cogs import cog_manager
from main import get_guild_prefix, System

if __name__ == '__main__':
    # Callable function needs signature of (cmd.Bot, discord.Message)
    _bot = cmd.Bot(command_prefix=get_guild_prefix, self_bot=True,
                   owner_id=612101930985979925)
    cog_manager.add_cogs(_bot, ['error', System, 'vc_log', 'Misc'])
    with open('saves/primary_user_key.json') as file:
        foo = json.load(file)
    _bot.run(foo, bot=False)
