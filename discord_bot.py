import argparse
import asyncio
import logging

import discord.ext.commands as cmd

import database as db


def make_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    return parser


def main():
    args = make_argparse().parse_args()

    db.setup_logging(
        to_stdout=not args.quiet,
        local_level=(logging.DEBUG if args.debug else logging.INFO),
        # local_level=logging.DEBUG
    )
    logger = db.get_logger(__name__)

    bot = cmd.Bot()

    bot_info = db.get_json_data(__name__)
    bot.owner_ids = bot_info.get("owners", [])
    key = bot_info["key"]
    db.init_box(bot_info["crypt"])

    bot.load_extensions("system", *bot_info.get("extensions", []))

    del bot_info
    asyncio.run(db.init_tables())
    bot.run(key)
    db.delete_temp_file()
    logger.info("Shutdown Complete, End of Process")


if __name__ == "__main__":
    main()
