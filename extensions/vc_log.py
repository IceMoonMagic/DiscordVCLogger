"""Code to let a bot to track joins and disconnects of Discord voice channels"""

import datetime as dt
import enum
from collections.abc import Collection

import discord
import discord.ext.commands as cmds
from sqlalchemy.orm import Mapped, mapped_column

import database as db
import utils

logger = db.get_logger(__name__)

VOICE_STATE_CHANNELS = discord.VoiceChannel | discord.StageChannel


def setup(bot: cmds.Bot):
    """Adds the cog to the bot"""
    logger.info("Loading Cog: VC Log")
    bot.add_cog(VcLog(bot))


def teardown(bot: cmds.Bot):
    """Removes the cog from the bot"""
    logger.info("Unloading Cog: VC Log")
    bot.remove_cog(f"{VcLog.qualified_name}")


class VoiceStateChange(enum.Enum):
    server_deafen = "deaf", True
    server_undeafen = "deaf", False
    server_mute = "mute", True
    server_unmute = "mute", False
    self_deafen = "self_deaf", True
    self_undeafen = "self_deaf", False
    self_mute = "self_mute", True
    self_unmute = "self_mute", False
    start_stream = "self_stream", True
    end_stream = "self_stream", False
    start_video = "self_video", True
    end_video = "self_video", False
    suppressed = "suppress", True
    unsuppressed = "suppress", False
    speak_request_start = "requested_to_speak_at", True
    speak_request_end = "requested_to_speak_at", False
    enter_afk = "afk", True
    exit_afk = "afk", False
    channel_join = "channel", True
    channel_leave = "channel", False

    @property
    def opposite(self) -> "VoiceStateChange":
        """Get the VoiceStateChange that would 'undo' this one."""
        return self.__class__((self.value[0], not self.value[1]))

    @classmethod
    def find_changes(
        cls: "VoiceStateChange",
        old_state: discord.VoiceState,
        new_state: discord.VoiceState,
        simplify: bool = False,
    ) -> list["VoiceStateChange"]:
        """
        Find all the differences between two discord voice states.

        :param old_state: The old voice state.
        :param new_state: The new voice state.
        :param simplify: Weather or not to simply the return.
        This removes self_(un)mute if self_(un)deafen is present.
        :return: The applicable VoiceStateChanges as a list.
        """
        changes: list["VoiceStateChange"] = []
        for attr in old_state.__slots__[1:]:  # Skip 'guild_id'
            old_value = getattr(old_state, attr)
            new_value = getattr(new_state, attr)
            if old_value == new_value:
                continue

            if attr == "channel":
                if old_value is not None:
                    changes.append(cls((attr, False)))
                if new_value is not None:
                    changes.append(cls((attr, True)))
            else:
                changes.append(cls((attr, bool(new_value))))

        if simplify and len(changes) == 2:
            # The discord client also mutes a user when they deafen
            if cls.self_mute in changes and cls.self_deafen in changes:
                changes.remove(cls.self_mute)
            elif cls.self_unmute in changes and cls.self_undeafen in changes:
                changes.remove(cls.self_unmute)
        return changes


class VoiceStateChangeLog(db.Storable):
    __tablename__ = "VoiceStateChangeLog"
    __table_args__ = {"prefixes": ["TEMPORARY"]}

    guild_id: Mapped[int]
    channel_id: Mapped[int]
    user_id: Mapped[int]
    change_name: Mapped[str]
    change_value: Mapped[bool]
    time: Mapped[dt.datetime] = mapped_column(
        default=utils.utcnow, type_=db.TZDateTime
    )
    _p_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    @property
    def change(self) -> VoiceStateChange:
        return VoiceStateChange(self.change_name, self.change_value)


class VcLog(cmds.Cog):
    """Cog for monitoring who joined and left a VC"""

    def __init__(self, bot: cmds.Bot):
        self.bot = bot

    def is_channel_empty(self, channel_id: int) -> bool:
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            raise ValueError
        return len(set(channel.voice_states)) == 0

    @cmds.Cog.listener()
    async def on_ready(self):
        # Checks for users already in a Voice Channel when Bot reconnects
        await _log_reconciliation(self.bot)

    @cmds.is_owner()
    async def force_scan_vcs(self, ctx: discord.ApplicationContext):
        ctx.defer()
        await _log_reconciliation(self.bot)
        await ctx.respond(utils.make_embed(desc="Reconciled Logs", ctx=ctx))

    @cmds.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        old_state: discord.VoiceState,
        new_state: discord.VoiceState,
    ):
        """
        Trigger to update list if someone joined or left VC

        :param member: The member that triggered the voice state update
        :param old_state: The Voice State before the voice state update
        :param new_state: The Voice State after the voice state update
        """
        await _log_changes(member.guild.id, member.id, old_state, new_state)

    log_command_group = discord.SlashCommandGroup("vclog", "foo")

    @staticmethod
    def _determine_voice_channel(
        ctx: discord.ApplicationContext,
        channel: VOICE_STATE_CHANNELS = None,
    ) -> VOICE_STATE_CHANNELS | utils.ErrorEmbed:
        if isinstance(channel, VOICE_STATE_CHANNELS):
            return channel
        elif isinstance(ctx.channel, VOICE_STATE_CHANNELS):
            return ctx.channel
        elif ctx.user.voice is not None and isinstance(
            ctx.user.voice.channel, VOICE_STATE_CHANNELS
        ):
            return ctx.user.voice.channel
        else:
            return utils.make_error(
                title="Could not fetch VC Log",
                desc="You're not in a Voice Channel.",
            )

    @log_command_group.command()
    @utils.autogenerate_options
    async def joined(
        self,
        ctx: discord.ApplicationContext = None,
        *,
        channel: VOICE_STATE_CHANNELS | None = None,
        amount: int = -1,
        time_format: utils.time_format_option = "R",
    ):
        # async def joined(self, ctx: discord.ApplicationContext):
        """
        Shows who has joined a VC and how long ago. Default to your VC.

        :param ctx: Application Context form Discord.
        :param channel: Channel to get logs from.
        :param amount: Number of entries to show. -1 = all
        :param time_format: The character for the discord timestamp
        """
        await ctx.defer()
        if not (vc := self._determine_voice_channel(ctx, channel)):
            await ctx.respond(embed=vc)
        events = await fetch_channel_records(
            channel_ids=[vc.id],
            user_ids=list(vc.voice_states),
            changes=[VoiceStateChange.channel_join],
            amount=amount,
        )
        await ctx.respond(embed=_vc_log_embed(events, time_format, ctx))

    @log_command_group.command()
    @utils.autogenerate_options
    async def left(
        self,
        ctx: discord.ApplicationContext,
        *,
        channel: VOICE_STATE_CHANNELS | None = None,
        amount: int = -1,
        time_format: utils.time_format_option = "R",
    ):
        # async def left(self, ctx: discord.ApplicationContext):
        """
        Shows who have left a VC and how long ago. Defaults to your VC.

        :param ctx: Application Context form Discord.
        :param channel: Channel to get logs from.
        :param amount: Number of entries to show. -1 = all
        :param time_format: The character for the discord timestamp
        """
        await ctx.defer()
        if not (vc := self._determine_voice_channel(ctx, channel)):
            await ctx.respond(embed=vc)
        events = await fetch_channel_records(
            channel_ids=[vc.id],
            exclude_user_ids=list(vc.voice_states),
            changes=[VoiceStateChange.channel_leave],
            amount=amount,
        )
        await ctx.respond(embed=_vc_log_embed(events, time_format, ctx))

    @log_command_group.command()
    @utils.autogenerate_options
    async def all(
        self,
        ctx: discord.ApplicationContext,
        *,
        channel: VOICE_STATE_CHANNELS | None = None,
        amount: int = -1,
        remove_dupes: bool = True,
        remove_undo: bool = False,
        time_format: utils.time_format_option = "R",
    ):
        """
        Get all the logs from a VC. Defaults to your VC.

        :param ctx: Application Context form Discord.
        :param channel: Channel to get logs from.
        :param amount: Number of entries to show. -1 = all
        :param remove_dupes:
        Only show the most recent of the event type for the member
        :param remove_undo:
        Only show events that have been "undone" by a more recent event
        :param time_format: The time format to display the logs
        """
        await ctx.defer()
        if not remove_dupes and remove_undo:
            await ctx.respond(
                embed=utils.make_error(
                    "Invalid Arguments",
                    "`remove_undo` must be `False` "
                    "if `remove_dupes` is `False`",
                )
            )
        if not (vc := self._determine_voice_channel(ctx, channel)):
            await ctx.respond(embed=vc)
        events = await fetch_channel_records(
            channel_ids=[vc.id],
            remove_dupes=remove_dupes,
            remove_undo=remove_undo,
            amount=amount,
        )
        await ctx.respond(embed=_vc_log_embed(events, time_format, ctx))

    @log_command_group.command()
    @utils.autogenerate_options
    async def get(
        self,
        ctx: discord.ApplicationContext,
        include: discord.Option(str, choices=VoiceStateChange.__members__),
        include_alt: bool = True,
        *,
        channel: VOICE_STATE_CHANNELS = None,
        amount: int = -1,
        remove_dupes: bool = True,
        remove_undo: bool = False,
        include_present: bool = True,
        include_absent: bool = True,
        time_format: utils.time_format_option = "R",
    ):
        """
        Get specified logs from a VC. Defaults to your VC.

        :param ctx: Application Context form Discord.
        :param include: The VoiceStateChange type to display.
        :param include_alt: Display the "opposite" VSC type.
        :param channel: Channel to get logs from.
        :param amount: Number of entries to show. -1 = all
        :param include_present: Include members currently in selected VC
        :param include_absent: Include members not currently in selected VC
        :param remove_dupes:
        Only show the most recent of the event type for the member
        :param remove_undo:
        Only show events that have been "undone" by a more recent event
        :param time_format: The time format to display the logs
        """
        await ctx.defer()
        if not remove_dupes and remove_undo:
            await ctx.respond(
                embed=utils.make_error(
                    "Invalid Arguments",
                    "`remove_undo` must be `False` "
                    "if `remove_dupes` is `False`",
                )
            )
        vsc_types = [VoiceStateChange[include]]
        if include_alt:
            vsc_types.append(vsc_types[0].opposite)

        if not (vc := self._determine_voice_channel(ctx, channel)):
            await ctx.respond(embed=vc)

        # ToDo: Find way to not have three *slightly* different calls
        if include_present and include_absent:
            events = await fetch_channel_records(
                channel_ids=[vc.id],
                changes=[VoiceStateChange.channel_join],
                remove_dupes=remove_dupes,
                remove_undo=remove_undo,
                amount=amount,
            )
        elif include_present:
            events = await fetch_channel_records(
                channel_ids=[vc.id],
                user_ids=list(vc.voice_states),
                changes=[VoiceStateChange.channel_join],
                remove_dupes=remove_dupes,
                remove_undo=remove_undo,
                amount=amount,
            )
        elif include_absent:
            events = await fetch_channel_records(
                channel_ids=[vc.id],
                exclude_user_ids=list(vc.voice_states),
                changes=[VoiceStateChange.channel_join],
                remove_dupes=remove_dupes,
                remove_undo=remove_undo,
                amount=amount,
            )
        else:
            events = []
        await ctx.respond(embed=_vc_log_embed(events, time_format, ctx))


async def _log_changes(
    guild_id: int,
    member_id: int,
    old_state: discord.VoiceState,
    new_state: discord.VoiceState,
):
    time = utils.utcnow()
    for change in VoiceStateChange.find_changes(old_state, new_state):
        if change == VoiceStateChange.channel_leave:
            if len(old_state.channel.voice_states) == 0:
                await VoiceStateChangeLog.delete_all(
                    VoiceStateChangeLog.channel_id == old_state.channel.id
                )
                continue
            channel_id = old_state.channel.id
        else:
            channel_id = new_state.channel.id
        await VoiceStateChangeLog(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=member_id,
            change_name=change.value[0],
            change_value=change.value[1],
            time=time,
        ).save()


async def _log_reconciliation(bot: discord.Bot):
    presumed_state_data = {
        "guild_id": "",
        "deaf": False,
        "mute": False,
        "self_mute": False,
        "self_stream": False,
        "self_video": False,
        "self_deaf": False,
        "afk": False,
        "channel": None,
        "requested_to_speak_at": None,
        "suppress": False,
    }
    await VoiceStateChangeLog.delete_all()
    for guild in bot.guilds:
        for voice_channel in guild.voice_channels:
            # if len(voice_channel.voice_states) == 0:
            #     await VoiceStateChangeLog.delete_all(
            #         channel_id=voice_channel.id)
            #     continue

            # ToDo: Get current estimated state
            # channel_events = await VoiceStateChangeLog.load_all(
            #     channel_id=voice_channel.id)
            # member_events: dict[int, list[VoiceStateChange]] = {}
            #
            # for event in channel_events:
            #     member_events[event.user_id] = member_events.get(
            #         event.user_id, []) + [event.change_name]
            #
            # for member_id, voice_state in voice_channel.voice_states:
            #     for event in member_events[member_id]:

            for member_id, voice_state in voice_channel.voice_states.items():
                presumed_state = discord.VoiceState(data=presumed_state_data)
                await _log_changes(
                    guild_id=guild.id,
                    member_id=member_id,
                    old_state=presumed_state,
                    new_state=voice_state,
                )


async def fetch_channel_records(
    guild_ids: list[int] = None,
    channel_ids: list[int] = None,
    user_ids: list[int] = None,
    exclude_user_ids: list[int] = None,
    changes: list[VoiceStateChange] = None,
    remove_dupes: bool = False,
    remove_undo: bool = False,
    amount: int = -1,
) -> list[VoiceStateChangeLog]:
    """
    Fetches a group of VoiceStateChangeLogs

    :param guild_ids: Only fetch records from <guilds>
    :param channel_ids: Only fetch records from <channels>
    :param user_ids: Only fetch records from <users>
    :param exclude_user_ids: Ignore records from <users>
    :param changes: Only fetch records of <VoiceStateChanges>
    :param remove_dupes:
    Only fetch the most recent of the event per type per toggle per member
    :param remove_undo: Don't consider toggle on / off with remove_dupes
    :param amount: Number of events to show (in reverse chronological order)
    :return: List of fetched VoiceStateChangeLogs
    """
    # SQLAlchemy doesn't seem to like `select(A).select(B)`,
    # so can't move this down to other remove_dupes / remove_undo checks
    if remove_dupes or remove_undo:
        stmt = db.select(
            VoiceStateChangeLog, db.func.max(VoiceStateChangeLog.time)
        ).order_by(VoiceStateChangeLog.time.desc())
    else:
        stmt = db.select(
            VoiceStateChangeLog,
        ).order_by(VoiceStateChangeLog.time.desc())

    if guild_ids:
        stmt = stmt.where(VoiceStateChangeLog.guild_id.in_(guild_ids))
    if channel_ids:
        stmt = stmt.where(VoiceStateChangeLog.channel_id.in_(channel_ids))
    if user_ids:
        stmt = stmt.where(VoiceStateChangeLog.user_id.in_(user_ids))
    if exclude_user_ids:
        stmt = stmt.where(VoiceStateChangeLog.user_id.notin_(exclude_user_ids))
    if changes:
        # TODO
        stmt = stmt.where(
            db.func.concat(
                VoiceStateChangeLog.change_name,
                VoiceStateChangeLog.change_value,
            ).in_(
                # Assumes db stores bools as ints 0 and 1, like SQLite
                [db.func.concat(c.value[0], int(c.value[1])) for c in changes]
            )
        )
    if amount > -1:
        stmt = stmt.limit(amount)

    if remove_dupes and remove_undo:
        # Gets only the most recent action
        # per class, ignoring toggle on / off per user
        stmt = stmt.group_by(
            VoiceStateChangeLog.user_id, VoiceStateChangeLog.change_name
        )
    elif remove_dupes:
        # Gets only the most recent action
        # per class per toggle on / off per user
        stmt = stmt.group_by(
            VoiceStateChangeLog.user_id,
            db.func.concat(
                VoiceStateChangeLog.change_name,
                VoiceStateChangeLog.change_value,
            ),
        )
    elif remove_undo:
        # Gets every action per class that is the most recent toggle?
        raise ValueError

    async with db.AsyncSession(db.ENGINE) as session:
        print(stmt)
        return list((await session.scalars(stmt)).all())


def _vc_log_embed(
    events: list[VoiceStateChangeLog],
    time_format: utils.TimestampStyle = "R",
    ctx: discord.ApplicationContext = None,
) -> discord.Embed:
    """
    Creates an embed for the given logs

    :param events: The events to embed
    :param time_format: The character for the discord timestamp
    :return: An embed of the given logs
    """
    fields = {}
    for event in events:
        existing = fields.get(event.change.name, "")
        mention = f"<@{event.user_id}>"
        time_str = utils.format_dt(event.time, time_format)
        line = f"- {mention} {time_str}\n"
        if len(existing + line) > 1023:
            fields[event.change_name] = existing + "+"
        else:
            fields[event.change_name] = existing + line

    embed = utils.make_embed(title=f"Voice Event History", ctx=ctx)
    for field, event_str in fields.items():
        # ToDo: Inline with opposite
        embed.add_field(
            name=field.replace("_", " ").title() + "s",
            value=fields.get(field, "- None"),
            inline=False,
        )
    if len(embed.fields) == 0:
        embed.description = "No logs present."
    return embed
