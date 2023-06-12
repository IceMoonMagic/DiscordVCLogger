"""Code to let a bot to track joins and disconnects of Discord voice channels"""
import dataclasses as dc
import enum
from collections.abc import Collection
from datetime import datetime, timezone

import discord
import discord.ext.commands as cmds

import database as db
import system

logger = db.get_logger(__name__)

VOICE_STATE_CHANNELS = discord.VoiceChannel | discord.StageChannel


def setup(bot: cmds.Bot):
    """Adds the cog to the bot"""
    logger.info('Loading Cog: VC Log')
    bot.add_cog(VcLog(bot))


def teardown(bot: cmds.Bot):
    """Removes the cog from the bot"""
    logger.info('Unloading Cog: VC Log')
    bot.remove_cog(f'{VcLog.qualified_name}')


class VoiceStateChange(enum.Enum):
    server_deafen = 'deaf', True
    server_undeafen = 'deaf', False
    server_mute = 'mute', True
    server_unmute = 'mute', False
    self_deafen = 'self_deaf', True
    self_undeafen = 'self_deaf', False
    self_mute = 'self_mute', True
    self_unmute = 'self_mute', False
    start_stream = 'self_stream', True
    end_stream = 'self_stream', False
    start_video = 'self_video', True
    end_video = 'self_video', False
    suppressed = 'suppress', True
    unsuppressed = 'suppress', False
    speak_request_start = 'requested_to_speak_at', True
    speak_request_end = 'requested_to_speak_at', False
    enter_afk = 'afk', True
    exit_afk = 'afk', False
    channel_join = 'channel', True
    channel_leave = 'channel', False

    @property
    def opposite(self) -> 'VoiceStateChange':
        """Get the VoiceStateChange that would 'undo' this one."""
        return self.__class__((self.value[0], not self.value[1]))

    @classmethod
    def find_changes(
            cls: 'VoiceStateChange',
            old_state: discord.VoiceState,
            new_state: discord.VoiceState,
            simplify: bool = False) \
            -> list['VoiceStateChange']:
        """
        Find all the differences between two discord voice states.

        :param old_state: The old voice state.
        :param new_state: The new voice state.
        :param simplify: Weather or not to simply the return.
        This removes self_(un)mute if self_(un)deafen is present.
        :return: The applicable VoiceStateChanges as a list.
        """
        changes: list['VoiceStateChange'] = []
        for attr in old_state.__slots__[1:]:  # Skip 'guild_id'
            old_value = getattr(old_state, attr)
            new_value = getattr(new_state, attr)
            if old_value == new_value:
                continue

            if attr == 'channel':
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


@dc.dataclass(frozen=True)
class VoiceStateChangeLog(db.Storable):
    primary_key_name = '_p_key'
    temp = True

    guild_id: int
    channel_id: int
    user_id: int
    change_name: str
    time: datetime = dc.field(
        default_factory=lambda: datetime.now(tz=timezone.utc))
    _p_key: int = dc.field(default=None)

    def __post_init__(self: db.S) -> db.S:
        if self._p_key is None:
            object.__setattr__(self, '_p_key', hash(self))
        return super().__post_init__()

    def __hash__(self):
        return hash(f'{self.guild_id}'
                    f'{self.channel_id}'
                    f'{self.user_id}'
                    f'{self.change_name}'
                    f'{self.time.timestamp()}')

    @property
    def change(self) -> VoiceStateChange:
        return getattr(VoiceStateChange, self.change_name)


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
        await ctx.respond(system.make_embed(desc='Reconciled Logs', ctx=ctx))

    @cmds.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    old_state: discord.VoiceState,
                                    new_state: discord.VoiceState):
        """
        Trigger to update list if someone joined or left VC

        :param member: The member that triggered the voice state update
        :param old_state: The Voice State before the voice state update
        :param new_state: The Voice State after the voice state update
        """
        await _log_changes(member.guild.id, member.id, old_state, new_state)

    log_command_group = discord.SlashCommandGroup("vclog", "foo")

    @log_command_group.command()
    @system.autogenerate_options
    async def joined(self, ctx: discord.ApplicationContext = None, *,
                     channel: VOICE_STATE_CHANNELS | None = None,
                     amount: int = -1,
                     time_format: system.time_parameter('R')):
        # async def joined(self, ctx: discord.ApplicationContext):
        """
        Shows who has joined a VC and how long ago. Default to your VC.

        :param ctx: Application Context form Discord.
        :param channel: Channel to get logs from.
        :param amount: Number of entries to show. -1 = all
        :param time_format: The character for the discord timestamp
        """
        await ctx.defer()
        await ctx.respond(embed=await _vc_log_embed(
            ctx=ctx,
            vsc_types=[VoiceStateChange.channel_join],
            amount=amount,
            channel=channel,
            ignore_empty=False,
            only_present=True,
            time_format=time_format))

    @log_command_group.command()
    @system.autogenerate_options
    async def left(self, ctx: discord.ApplicationContext, *,
                   channel: VOICE_STATE_CHANNELS | None = None,
                   amount: int = -1,
                   time_format: system.time_parameter('R')):
        # async def left(self, ctx: discord.ApplicationContext):
        """
        Shows who have left a VC and how long ago. Defaults to your VC.

        :param ctx: Application Context form Discord.
        :param channel: Channel to get logs from.
        :param amount: Number of entries to show. -1 = all
        :param time_format: The character for the discord timestamp
        """
        await ctx.defer()
        await ctx.respond(embed=await _vc_log_embed(
            ctx=ctx,
            vsc_types=[VoiceStateChange.channel_leave],
            amount=amount,
            channel=channel,
            ignore_empty=False,
            only_present=None,
            time_format=time_format))

    @log_command_group.command()
    @system.autogenerate_options
    async def all(self, ctx: discord.ApplicationContext, *,
                  channel: VOICE_STATE_CHANNELS | None = None,
                  amount: int = -1, ignore_empty: bool = True,
                  remove_dupes: bool = True, remove_undo: bool = True,
                  time_format: system.time_parameter('R')):
        """
        Get all the logs from a VC. Defaults to your VC.

        :param ctx: Application Context form Discord.
        :param channel: Channel to get logs from.
        :param amount: Number of entries to show. -1 = all
        :param ignore_empty: Weather or not to hide empty categories.
        :param remove_dupes:
        Only show the most recent of the event type for the member
        :param remove_undo:
        Only show events that have been "undone" by a more recent event
        :param time_format: The time format to display the logs
        """
        await ctx.defer()
        await ctx.respond(embed=await _vc_log_embed(
            ctx=ctx,
            amount=amount,
            channel=channel,
            ignore_empty=ignore_empty,
            only_present=False,
            remove_dupes=remove_dupes,
            remove_undo=remove_undo,
            time_format=time_format))

    @log_command_group.command()
    @system.autogenerate_options
    async def get(self, ctx: discord.ApplicationContext,
                  include: discord.Option(
                      str, choices=VoiceStateChange.__members__),
                  include_alt: bool = True, *,
                  channel: VOICE_STATE_CHANNELS = None,
                  amount: int = -1, ignore_empty: bool = False,
                  remove_dupes: bool = True, remove_undo: bool = True,
                  only_present: bool = False,
                  time_format: system.time_format_option = 'R',
                  ):
        """
        Get specified logs from a VC. Defaults to your VC.

        :param ctx: Application Context form Discord.
        :param include: The VoiceStateChange type to display.
        :param include_alt: Display the "opposite" VSC type.
        :param channel: Channel to get logs from.
        :param amount: Number of entries to show. -1 = all
        :param ignore_empty: Weather or not to hide empty categories.
        :param only_present: Skip members not in selected VC
        :param remove_dupes:
        Only show the most recent of the event type for the member
        :param remove_undo:
        Only show events that have been "undone" by a more recent event
        :param time_format: The time format to display the logs
        """
        await ctx.defer()
        vsc_types = [VoiceStateChange[include]]
        if include_alt:
            vsc_types.append(vsc_types[0].opposite)

        await ctx.respond(embed=await _vc_log_embed(
            ctx=ctx,
            vsc_types=vsc_types,
            amount=amount,
            channel=channel,
            ignore_empty=ignore_empty,
            only_present=only_present,
            remove_dupes=remove_dupes,
            remove_undo=remove_undo,
            time_format=time_format))


async def _log_changes(
        guild_id: int,
        member_id: int,
        old_state: discord.VoiceState,
        new_state: discord.VoiceState):
    time = datetime.now(tz=timezone.utc)
    for change in VoiceStateChange.find_changes(old_state, new_state):
        if change == VoiceStateChange.channel_leave:
            if len(old_state.channel.voice_states) == 0:
                await VoiceStateChangeLog.delete_all(
                    channel_id=old_state.channel.id)
                continue
            channel_id = old_state.channel.id
        else:
            channel_id = new_state.channel.id
        await VoiceStateChangeLog(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=member_id,
            change_name=change.name,
            time=time).save()


async def _log_reconciliation(bot: discord.Bot):
    presumed_state_data = {
        'guild_id': '',
        "deaf": False,
        "mute": False,
        "self_mute": False,
        "self_stream": False,
        "self_video": False,
        "self_deaf": False,
        "afk": False,
        "channel": None,
        "requested_to_speak_at": None,
        "suppress": False
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
                    new_state=voice_state)


# ToDo: Breakup _vc_log_embed
async def _vc_log_embed(
        ctx: discord.ApplicationContext,
        vsc_types: Collection[VoiceStateChange] | None = None,
        amount: int = -1,
        only_present: bool | None = True,
        channel: VOICE_STATE_CHANNELS | None = None,
        time_format: str = 'R',
        ignore_empty: bool = True,
        remove_dupes: bool = True,
        remove_undo: bool = True) \
        -> discord.Embed:
    """
    Creates an embed with for the VC Log

    :param ctx: Application Context form Discord.
    :param vsc_types: VoiceStateChanges to include
    :param amount: Number of events to show (in reverse chronological order)
    :param only_present: Only include members in the selected voice channel
    :param channel: The Voice Channel to show the logs of
    :param time_format: The character for the discord timestamp
    :param ignore_empty: Ignore VoiceStateChanges that have no entries
    :param remove_dupes:
    Only show the most recent of the event type for the member
    :param remove_undo:
    Only show events that have been "undone" by a more recent event
    :return: An embed of the logs for the channel
    """
    if isinstance(channel, VOICE_STATE_CHANNELS):
        vc = channel
    elif isinstance(ctx.channel, VOICE_STATE_CHANNELS):
        vc = ctx.channel
    elif isinstance(ctx.user.voice.channel, VOICE_STATE_CHANNELS):
        vc = ctx.user.voice.channel
    else:
        return system.make_error(
            title='Could not fetch VC Log',
            description='You\'re not in a Voice Channel.')

    voices = set(vc.voice_states)
    if only_present:
        options = {'user_id': voices}
    elif only_present is None:
        options = {'not_user_id': voices}
    else:
        options = {}

    if vsc_types is None or len(vsc_types) == 0:
        vsc_types: tuple[str] = tuple(VoiceStateChange.__members__)
    else:
        vsc_types: tuple[str] = tuple(vsc.name for vsc in vsc_types)

    events = await VoiceStateChangeLog.load_all(
        channel_id=vc.id,
        change_name=[vsc for vsc in vsc_types],
        **options)

    if amount == -1:
        amount = len(events)
    iterator = (e for i, e in zip(range(amount), reversed(events)))

    fields = {}
    for event in iterator:
        existing = fields.get(event.change_name, '')
        mention = f'<@{event.user_id}>'
        if (remove_dupes and mention in existing) or \
                (remove_undo and mention in
                 fields.get(event.change.opposite.name, '')):
            continue
        time_str = system.get_time_str(event.time, time_format)
        line = f'- {mention} {time_str}\n'
        if len(existing + line) > 1023:
            fields[event.change_name] = existing + '+'
        else:
            fields[event.change_name] = existing + line

    embed = system.make_embed(
        title=f'Voice Event history in `{vc.name}`:', ctx=ctx)
    for field in vsc_types:
        if ignore_empty and field not in fields:
            continue
        # ToDo: Inline with opposite
        embed.add_field(
            name=field.replace('_', ' ').title() + 's',
            value=fields.get(field, '- None'),
            inline=False)
    if len(embed.fields) == 0:
        embed.description = 'No logs present.'
    return embed
