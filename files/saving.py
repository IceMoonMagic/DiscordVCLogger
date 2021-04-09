"""Manages Saving and Loading for the Bot"""

import json
import logging
from typing import Dict

logger = logging.getLogger(__name__)

_SAVE_DIRECTORY = 'saves'
"""Directory to store save files"""
_PREFIX_FILE = f'{_SAVE_DIRECTORY}/guild_prefixes.json'
"""File to store guild prefixes"""
_BOT_KEY_FILE = f'{_SAVE_DIRECTORY}/bot_key.json'


def guild_prefixes_load() -> Dict[int, str]:
    """
    Loads the prefixes for the guilds from PREFIX_FILE

    :return: Dict of [Guild ID, prefix]
    """
    logger.info('Loading guild prefixes')
    with open(_PREFIX_FILE) as file:
        str_dict = json.load(file)
        return {int(k): v for k, v in str_dict.items()}


def guild_prefixes_save(data: Dict[int, str]) -> None:
    """
    Saves the prefixes for the guilds to PREFIX_FILE

    :param data: Dict of [Guild ID, prefix]
    :return: None
    """
    logger.info('Saving guild prefixes')
    with open(_PREFIX_FILE, 'w') as file:
        file.seek(0)
        file.truncate()
        json.dump(data, file, indent=4)


def bot_key_load() -> str:
    """Gets the bot key from BOT_KEY"""
    logger.info('Loading bot key')
    with open(_BOT_KEY_FILE) as file:
        return json.load(file)
