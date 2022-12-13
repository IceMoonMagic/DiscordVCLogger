import re
from asyncio import create_task
from typing import Coroutine

import discord
import discord.ext.commands as cmd
from discord import ApplicationCommand, ApplicationContext

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


bot = cmd.Bot(intents=intents)


@bot.listen()
async def on_ready():
    """Final Setup after Bot is fully connected to Discord"""
    logger.info(f'Logged in as {bot.user.id} ({bot.user}).')


@bot.listen()
async def on_command(ctx: cmd.Context):
    """Logs attempted execution of a command."""
    logger.info(f'Command [{ctx.command.qualified_name}] invoked by'
                f' {ctx.author.id} ({ctx.author.display_name})')


@bot.listen()
async def on_application_command(ctx: discord.ApplicationContext):
    """Logs attempted execution of a command."""
    logger.info(f'User {ctx.author.id} invoked {ctx.command.qualified_name}')


shutdown_coroutines: list[Coroutine] = []


def add_shutdown_step(coro: Coroutine):
    shutdown_coroutines.append(coro)


@bot.slash_command(name='shutdown')
async def shutdown_command(ctx: discord.ApplicationContext):
    """Does necessary actions to end execution of the bot."""
    logger.info('Beginning shutdown process.')

    await ctx.defer()

    tasks = []  # Python 3.11 ToDo: asyncio.TaskGroup
    for coro in shutdown_coroutines:
        tasks.append(create_task(coro))
    for task in tasks:
        await task

    await ctx.respond(embed=discord.Embed(
        title='Shutting Down'))
    await bot.close()


@bot.listen()
async def on_application_command_error(
        ctx: ApplicationContext, error: discord.ApplicationCommandError):
    """Catches when a command throws an error."""
    await ctx.defer()
    raise_it = False

    match error:
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
            if isinstance(error, cmd.BotMissingPermissions):
                title = f'Bot {title}'
            for i, permission in enumerate(error.missing_permissions):
                if i != 0:
                    desc += '\n'
                desc += f' - {permission}'

        case cmd.NotOwner():
            title = 'Not Owner'
            desc = f'Only bot owners can use this command.'

        case cmd.CheckFailure():
            title = 'Check Error'
            desc = 'There is some condition that is not being met.'

        case _:
            title = 'Unexpected Command Error'
            desc = f'If this issue persists, please inform ' \
                   f'<@{bot.owner_ids[0]}>.'
            raise_it = True

    logger.warning(
        f'Command Error: {ctx.author.id}'
        f' invoked {ctx.command.qualified_name}'
        f' which raised a(n) {type(error)}.')

    await ctx.respond(embed=make_error(title, desc))

    if raise_it:
        raise error


async def get_dm(user_id: int, _bot: cmd.Bot = bot) -> discord.DMChannel:
    user = await _bot.get_or_fetch_user(user_id)
    return user.dm_channel or await user.create_dm()


def make_embed(title: str = None, desc: str = None,
               ctx: ApplicationContext = None,
               color: discord.Color = None,
               embed: discord.Embed = None,
               **kwargs) -> discord.Embed:
    """Creates a uniform standard embed for other methods to send."""
    if embed is not None:
        title = embed.title if title is None else title
        desc = embed.description if desc is None else desc
        color = embed.color if ctx is None and color is None else color
    else:
        title = 'Generic Title' if title is None else title
        desc = 'Generic Description' if desc is None else desc

    if color:
        apply_color = color
    elif ctx:
        apply_color = ctx.me.color
    else:
        apply_color = discord.Color.blurple()

    return discord.Embed(title=title, description=desc,
                         color=apply_color, **kwargs)


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
    docstring = re.sub(r'\s+', ' ', fn.__doc__).strip()
    params = docstring.split(':param ')[1:]
    for param in params:
        name, docs = re.findall(r'([\w\d]+):\s([\w\W]+)', param)[0]
        anno = fn.__annotations__.get(name) or str
        match anno:
            case discord.ApplicationContext() | discord.Interaction():
                continue
            case discord.Option():
                if anno.description == 'No description provided':
                    anno.description = docs
            case _:
                fn.__annotations__[name] = discord.Option(
                    anno, description=docs)
    return fn
