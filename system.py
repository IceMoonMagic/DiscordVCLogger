from asyncio import TaskGroup
from typing import Coroutine

import discord
import discord.ext.commands as cmd
import discord.ui
import nacl.exceptions

import database as db
import utils

# https://docs.pycord.dev/en/stable/api.html?highlight=intents#discord.Intents
intents = discord.Intents(
    guilds=True,
    members=True,
    bans=False,
    emojis_and_stickers=False,
    integrations=False,
    webhooks=False,
    invites=False,
    voice_states=True,
    presences=False,
    messages=True,
    reactions=False,
    typing=False,
    message_content=False,
    # scheduled_events=False,
    auto_moderation_configuration=False,
    auto_moderation_execution=False,
)

logger = db.get_logger(__name__)


def setup(bot: cmd.Bot):
    logger.info(f"Loading Extension: {__name__}")
    bot.add_cog(System(bot))


def teardown(bot: cmd.Bot):
    logger.info(f"Unloading Extension: {__name__}")
    bot.remove_cog(System.qualified_name)


class System(cmd.Cog):
    def __init__(self, bot: cmd.Bot):
        self.bot: cmd.Bot = bot
        self.shutdown_coroutines: list[Coroutine] = []

    system_cmds = discord.SlashCommandGroup("system")

    @cmd.is_owner()
    @system_cmds.command(name="shutdown")
    async def shutdown_command(self, ctx: discord.ApplicationContext):
        """Does necessary actions to end execution of the bot."""
        logger.info("Beginning shutdown process.")

        await ctx.defer()

        async with TaskGroup() as tg:
            for coro in self.shutdown_coroutines:
                tg.create_task(coro)

        await ctx.respond(embed=discord.Embed(title="Shutting Down"))
        await self.bot.close()

    @cmd.is_owner()
    @system_cmds.command(name="ip")
    async def get_ip(self, ctx: discord.ApplicationContext):
        """Gets the *local* IP address of the host machine"""
        logger.info("Getting IP Address")

        await ctx.defer(ephemeral=True)

        import socket

        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        await ctx.respond(
            embed=utils.make_embed(f"Local IP Address", ip, ctx=ctx),
            ephemeral=True,
        )

    @cmd.Cog.listener()
    async def on_ready(self):
        """Final Setup after Bot is fully connected to Discord"""
        logger.info(f"Logged in as {self.bot.user.id} ({self.bot.user}).")

    @cmd.Cog.listener()
    async def on_application_command(self, ctx: discord.ApplicationContext):
        """Logs attempted execution of a command."""
        logger.info(
            f"User {ctx.author.id} invoked {ctx.command.qualified_name}"
        )

    @cmd.Cog.listener()
    async def on_application_command_error(
        self, ctx: discord.ApplicationContext, error: discord.DiscordException
    ):
        """Catches when a command throws an error."""
        try:
            await ctx.defer()
        except discord.InteractionResponded:
            pass
        raise_it = False

        cause: Exception
        if isinstance(error, discord.ApplicationCommandInvokeError):
            cause = error.original
        else:
            cause = error

        match cause:
            case cmd.CommandNotFound():
                return

            case cmd.DisabledCommand():
                await ctx.respond(
                    embed=utils.make_error(
                        "Command is Disabled",
                        f"Command `{ctx.command.qualified_name}` is "
                        f"disabled and therefore cannot be used.",
                    )
                )
                return

            case cmd.MissingPermissions() | cmd.BotMissingPermissions():
                title, desc = "Missing Permissions", ""
                if isinstance(cause, cmd.BotMissingPermissions):
                    title = f"Bot {title}"
                for i, permission in enumerate(cause.missing_permissions):
                    if i != 0:
                        desc += "\n"
                    desc += f" - {permission}"

            case cmd.NotOwner():
                title = "Not Owner"
                desc = f"Only bot owners can use this command."

            case cmd.CheckFailure() | discord.errors.CheckFailure():
                title = "Check Error"
                desc = "There is some condition that is not being met."

            case db.MissingEncryptionKey():
                table_name = cause.storable.table_name
                class_name = cause.storable.__class__.__name__
                if table_name == class_name:
                    table = table_name
                else:
                    table = f"{class_name} / {table_name}"

                title = "Missing Encryption Key"
                desc = (
                    f"Unable to encrypt/decrypt data for {table}. "
                    f"Please inform <@{self.bot.owner_ids[0]}>."
                )

            case nacl.exceptions.CryptoError():
                title = "Crypto Error"
                desc = (
                    "This likely means that the current encryption "
                    "key is different than when you stored your data. "
                    "Please resubmit the necessary data to resume usage."
                )

            case _:
                title = "Unexpected Command Error"
                desc = (
                    f"If this issue persists, please inform "
                    f"<@{self.bot.owner_ids[0]}>."
                )
                raise_it = True

        logger.warning(
            f"Command Error: {ctx.author.id}"
            f" invoked {ctx.command.qualified_name}"
            f" which raised a(n) {type(cause)}."
        )

        await ctx.respond(embed=utils.make_error(title, desc))

        if raise_it:
            raise cause


def add_shutdown_step(bot: cmd.Bot, coro: Coroutine):
    foo = bot.get_cog(System.qualified_name)
    if isinstance(foo, System):
        foo.shutdown_coroutines.append(coro)
