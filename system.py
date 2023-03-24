import re
from asyncio import create_task
from datetime import datetime
from typing import Any, Coroutine, Callable

import discord
import discord.ext.commands as cmd
import discord.ui
import nacl.exceptions

import database as db

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
    logger.info(f'Loading Extension: {__name__}')
    bot.add_cog(System(bot))


def teardown(bot: cmd.Bot):
    logger.info(f'Unloading Extension: {__name__}')
    bot.remove_cog(System.qualified_name)


class System(cmd.Cog):

    def __init__(self, bot: cmd.Bot):
        self.bot: cmd.Bot = bot
        self.shutdown_coroutines: list[Coroutine] = []

    system_cmds = discord.SlashCommandGroup('system')

    @cmd.is_owner()
    @system_cmds.command(name='shutdown')
    async def shutdown_command(self, ctx: discord.ApplicationContext):
        """Does necessary actions to end execution of the bot."""
        logger.info('Beginning shutdown process.')

        await ctx.defer()

        tasks = []  # Python 3.11 ToDo: asyncio.TaskGroup
        for coro in self.shutdown_coroutines:
            tasks.append(create_task(coro))
        for task in tasks:
            await task

        await ctx.respond(embed=discord.Embed(
            title='Shutting Down'))
        await self.bot.close()

    @cmd.is_owner()
    @system_cmds.command(name='ip')
    async def get_ip(self, ctx: discord.ApplicationContext):
        """Gets the *local* IP address of the host machine"""
        logger.info('Getting IP Address')

        await ctx.defer(ephemeral=True)

        import socket
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        await ctx.respond(
            embed=make_embed(f'Local IP Address', ip, ctx=ctx),
            ephemeral=True)

    @cmd.Cog.listener()
    async def on_ready(self):
        """Final Setup after Bot is fully connected to Discord"""
        logger.info(f'Logged in as {self.bot.user.id} ({self.bot.user}).')

    @cmd.Cog.listener()
    async def on_application_command(self, ctx: discord.ApplicationContext):
        """Logs attempted execution of a command."""
        logger.info(
            f'User {ctx.author.id} invoked {ctx.command.qualified_name}')

    @cmd.Cog.listener()
    async def on_application_command_error(
            self,
            ctx: discord.ApplicationContext,
            error: discord.DiscordException):
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
                await ctx.respond(embed=make_error(
                    'Command is Disabled',
                    f'Command `{ctx.command.qualified_name}` is '
                    f'disabled and therefore cannot be used.'))
                return

            case cmd.MissingPermissions() | cmd.BotMissingPermissions():
                title, desc = 'Missing Permissions', ''
                if isinstance(cause, cmd.BotMissingPermissions):
                    title = f'Bot {title}'
                for i, permission in enumerate(cause.missing_permissions):
                    if i != 0:
                        desc += '\n'
                    desc += f' - {permission}'

            case cmd.NotOwner():
                title = 'Not Owner'
                desc = f'Only bot owners can use this command.'

            case cmd.CheckFailure() | discord.errors.CheckFailure():
                title = 'Check Error'
                desc = 'There is some condition that is not being met.'

            case db.MissingEncryptionKey():
                table_name = cause.storable.table_name
                class_name = cause.storable.__class__.__name__
                if table_name == class_name:
                    table = table_name
                else:
                    table = f'{class_name} / {table_name}'

                title = 'Missing Encryption Key'
                desc = f'Unable to encrypt/decrypt data for {table}. ' \
                       f'Please inform <@{self.bot.owner_ids[0]}>.'

            case nacl.exceptions.CryptoError():
                title = 'Crypto Error'
                desc = 'This likely means that the current encryption ' \
                       'key is different than when you stored your data. ' \
                       'Please resubmit the necessary data to resume usage.'

            case _:
                title = 'Unexpected Command Error'
                desc = f'If this issue persists, please inform ' \
                       f'<@{self.bot.owner_ids[0]}>.'
                raise_it = True

        logger.warning(
            f'Command Error: {ctx.author.id}'
            f' invoked {ctx.command.qualified_name}'
            f' which raised a(n) {type(cause)}.')

        await ctx.respond(embed=make_error(title, desc))

        if raise_it:
            raise cause


def add_shutdown_step(bot: cmd.Bot, coro: Coroutine):
    foo = bot.get_cog(System.qualified_name)
    if isinstance(foo, System):
        foo.shutdown_coroutines.append(coro)


async def get_dm(user_id: int, bot: cmd.Bot) -> discord.DMChannel:
    user = await bot.get_or_fetch_user(user_id)
    return user.dm_channel or await user.create_dm()


def make_embed(title: str = None, desc: str = None,
               ctx: discord.ApplicationContext = None,
               color: discord.Color = None,
               embed: discord.Embed = None,
               **kwargs) -> discord.Embed:
    """Creates a uniform standard embed for other methods to send."""
    if embed is not None:
        title = embed.title if title is None else title
        desc = embed.description if desc is None else desc
        color = embed.color if ctx is None and color is None else color

    if title:
        kwargs.update({'title': title})
    if desc:
        kwargs.update({'description': desc})

    if color:
        kwargs.update({'color': color})
    elif ctx:
        kwargs.update({'color': ctx.me.color})
    else:
        kwargs.update({'color': discord.Color.blurple()})

    return discord.Embed(**kwargs)


class ErrorEmbed(discord.Embed):

    def __bool__(self):
        return False


def make_error(title: str = 'Error', desc: str = 'Generic Error', **kwargs) \
        -> ErrorEmbed:
    """Creates a uniform error embed for other methods to send."""
    return ErrorEmbed(
        title=title, description=desc,
        color=discord.Color.dark_red(), **kwargs)


def autogenerate_options(fn):
    if not fn.__doc__:
        return fn
    none_type = type(None)
    docstring = re.sub(r'\s+', ' ', fn.__doc__).strip()
    params = docstring.split(':param ')[1:]
    for param in params:
        name, docs = re.findall(r'([\w\d]+):\s([\w\W]+)', param)[0]
        anno = fn.__annotations__.get(name) or str
        match anno:
            case discord.ApplicationContext | discord.Interaction:
                continue
            case discord.Option():
                if anno.description == 'No description provided':
                    anno.description = docs
            case _:
                if hasattr(anno, '__args__') and \
                        none_type in (anno := anno.__args__):
                    anno = tuple(a for a in anno if a != none_type)
                if fn.__kwdefaults__ is None or name not in fn.__kwdefaults__:
                    option = discord.Option(
                        input_type=anno,
                        description=docs,
                        required=True)
                else:
                    option = discord.Option(
                        input_type=anno,
                        description=docs,
                        default=fn.__kwdefaults__.get(name))
                fn.__annotations__[name] = option
    return fn


def get_time_str(time: datetime | int,
                 time_format: str = '') -> str:
    if time_format not in {'', 't', 'T', 'd', 'D', 'f', 'F', 'R'}:
        raise ValueError(f'Unrecognized time format {time_format}')
    if isinstance(time, datetime):
        time = int(time.timestamp())
    return f'<t:{time}:{time_format}>'


class UnlockModal(discord.ui.Modal):

    def __init__(self, unlock_type: type[db.S], *children: discord.ui.InputText):
        super().__init__(*children, title=unlock_type.__name__)

        self.unlock_type = unlock_type

        self.add_item(discord.ui.InputText(
            label='Key',
            placeholder='key',
            min_length=32,
            max_length=32))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            self.unlock_type.set_key(self.children[0].value)
            await interaction.followup.send(
                ephemeral=True,
                embed=make_embed(
                    f'Unlocked {self.unlock_type.__name__}',
                    color=interaction.guild.me.color
                    if interaction.guild else None))
        except ValueError as e:
            await interaction.followup.send(
                ephemeral=True,
                embed=make_error(
                    f'Failed to unlock {self.unlock_type.__name__}',
                    f'{type(e).__name__}: {e}'))


async def send_dm(user_id: int, bot: cmd.Bot, *msg_args, **msg_kwargs):
    dm = await get_dm(user_id, bot)
    await dm.send(*msg_args, **msg_kwargs)


async def do_and_dm(user_id: int, bot: cmd.Bot,
                    coro: Coroutine[Any, Any, discord.Embed],
                    send: bool = True) -> discord.Embed:
    embed = await coro
    if send:
        await send_dm(user_id, bot, embed=embed)
    return embed
