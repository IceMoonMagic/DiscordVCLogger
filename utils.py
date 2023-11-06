import re
from typing import Coroutine, Any

import discord.utils
import discord.ext.commands as cmd

import database as db


sleep_until = discord.utils.sleep_until
utcnow = discord.utils.utcnow
format_dt = discord.utils.format_dt
parse_time = discord.utils.parse_time
TimestampStyle = discord.utils.TimestampStyle
time_format_option = discord.Option(
    str,
    default="R",
    choices=[
        discord.OptionChoice("Short Time", "t"),
        discord.OptionChoice("Long Time", "T"),
        discord.OptionChoice("Short Date", "d"),
        discord.OptionChoice("Long Date", "D"),
        discord.OptionChoice("Short Date/Time", "f"),
        discord.OptionChoice("Long Date/Time", "F"),
        discord.OptionChoice("Relative Time", "R"),
    ],
)


class ErrorEmbed(discord.Embed):
    def __bool__(self):
        return False


def make_error(
    title: str = "Error", desc: str = "Generic Error", **kwargs
) -> ErrorEmbed:
    """Creates a uniform error embed for other methods to send."""
    return ErrorEmbed(
        title=title, description=desc, color=discord.Color.dark_red(), **kwargs
    )


def make_embed(
    title: str = None,
    desc: str = None,
    ctx: discord.ApplicationContext = None,
    color: discord.Color = None,
    embed: discord.Embed = None,
    **kwargs,
) -> discord.Embed:
    """Creates a uniform standard embed for other methods to send."""
    if embed is not None:
        title = embed.title if title is None else title
        desc = embed.description if desc is None else desc
        color = embed.color if ctx is None and color is None else color

    if title:
        kwargs.update({"title": title})
    if desc:
        kwargs.update({"description": desc})

    if color:
        kwargs.update({"color": color})
    elif ctx:
        kwargs.update({"color": ctx.me.color})
    else:
        kwargs.update({"color": discord.Color.blurple()})

    return discord.Embed(**kwargs)


class UnlockModal(discord.ui.Modal):
    def __init__(
        self, unlock_type: type[db.S], *children: discord.ui.InputText
    ):
        super().__init__(*children, title=unlock_type.__name__)

        self.unlock_type = unlock_type

        self.add_item(
            discord.ui.InputText(
                label="Key", placeholder="key", min_length=32, max_length=32
            )
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            self.unlock_type.set_key(self.children[0].value)
            await interaction.followup.send(
                ephemeral=True,
                embed=make_embed(
                    f"Unlocked {self.unlock_type.__name__}",
                    color=interaction.guild.me.color
                    if interaction.guild
                    else None,
                ),
            )
        except ValueError as e:
            await interaction.followup.send(
                ephemeral=True,
                embed=make_error(
                    f"Failed to unlock {self.unlock_type.__name__}",
                    f"{type(e).__name__}: {e}",
                ),
            )


def autogenerate_options(fn):
    if not fn.__doc__:
        return fn
    none_type = type(None)
    docstring = re.sub(r"\s+", " ", fn.__doc__).strip()
    params = docstring.split(":param ")[1:]
    for param in params:
        name, docs = re.findall(r"(\w+):\s(.+)", param)[0]
        anno = fn.__annotations__.get(name) or str
        match anno:
            case discord.ApplicationContext | discord.Interaction:
                continue
            case discord.Option():
                if anno.description == "No description provided":
                    anno.description = docs
            case _:
                if hasattr(anno, "__args__") and none_type in (
                    anno := anno.__args__
                ):
                    anno = tuple(a for a in anno if a != none_type)
                if fn.__kwdefaults__ is None or name not in fn.__kwdefaults__:
                    option = discord.Option(
                        anno, description=docs, required=True
                    )
                else:
                    option = discord.Option(
                        anno,
                        description=docs,
                        default=fn.__kwdefaults__.get(name),
                    )
                fn.__annotations__[name] = option
    return fn


async def get_dm(user_id: int, bot: cmd.Bot) -> discord.DMChannel:
    user = await bot.get_or_fetch_user(user_id)
    return user.dm_channel or await user.create_dm()


async def send_dm(user_id: int, bot: cmd.Bot, *msg_args, **msg_kwargs):
    dm = await get_dm(user_id, bot)
    await dm.send(*msg_args, **msg_kwargs)


async def do_and_dm(
    user_id: int,
    bot: cmd.Bot,
    coro: Coroutine[Any, Any, discord.Embed],
    send: bool = True,
) -> discord.Embed:
    embed = await coro
    if send:
        await send_dm(user_id, bot, embed=embed)
    return embed
