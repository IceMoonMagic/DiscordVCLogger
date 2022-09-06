"""Code to let a bot to track joins and disconnects of Discord voice channels"""
# from __future__ import annotations

import dataclasses as dc
import enum
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Generator, List, Optional, Set, Union

import discord
import discord.ext.commands as cmd

from .cog_manager import Cog, get_time_str

# import tools

logger = logging.getLogger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info('Loading Cog: VC Log')
    bot.add_cog(VcLog(bot))


def teardown(bot: cmd.Bot):
    """Removes the cog from the bot"""
    logger.info('Unloading Cog: VC Log')
    bot.remove_cog(f'{VcLog.qualified_name}')


class VoiceStateChange(enum.Enum):
    # refreshing = enum.auto()
    server_deafen = 'server_undeafen'
    server_undeafen = 'server_deafen'
    server_mute = 'server_unmute'
    server_unmute = 'server_mute'
    self_deafen = 'self_undeafen'
    self_undeafen = 'self_deafen'
    self_mute = 'self_unmute'
    self_unmute = 'self_mute'
    start_stream = 'end_stream'
    end_stream = 'start_stream'
    start_video = 'end_video'
    end_video = 'start_video'
    # suppress = enum.auto()
    # suppress = enum.auto()
    # speak_request = enum.auto()
    # speak_request = enum.auto()
    # enter_afk = enum.auto()
    # exit_afk = enum.auto()
    channel_join = 'channel_leave'
    channel_leave = 'channel_join'

    @property
    def opposite(self) -> 'VoiceStateChange':
        return self.__class__(self.name)

    @property
    def verb(self) -> str:
        if 'start' in self.name or 'end' in self.name:
            return self.name.replace('_', 'ed ')
        elif 'channel' in self.name:
            string = self.name.replace('leave', 'left')
            string = string.replace('join', 'joined')
            return ' '.join(reversed(string.split('_')))
        else:
            return f"{self.name.replace('_', ' ')}ed".replace('eed', 'ed')

    # @staticmethod
    # def get_opposite(self, vsc: VoiceStateChange) -> VoiceStateChange:
    #     return VoiceStateChange(vsc.name)


class VcLog(Cog):
    """Cog for monitoring who joined and left a VC"""

    @dc.dataclass()
    class _VcLogData:
        """Stores the data for a VC"""

        # _present: list = dc.field(default_factory=list, init=False)
        # _absent: list = dc.field(default_factory=list, init=False)
        # _full_log: List[VoiceEvent] = dc.field(
        _full_log: Any = dc.field(
            default_factory=list, init=False)
        # member_count: int = dc.field(default=0, init=False)
        _members: Set[int] = dc.field(default_factory=set, init=False)

        @dc.dataclass(frozen=True)
        class VoiceEvent:
            """Bundles the Member and Time of a Voice Event"""
            member_id: int
            event_type: VoiceStateChange
            # executor_id: int = None
            time: datetime = dc.field(
                default_factory=lambda: datetime.now(timezone.utc))

            def __eq__(self, other):
                if isinstance(other, self.__class__):
                    return self.member_id == other.member_id
                elif isinstance(other, int):
                    return self.member_id == other
                else:
                    return NotImplemented

            def __hash__(self):
                h = [str(self.member_id), self.event_type.name,
                     self.event_type.opposite.name]
                h.sort()
                return hash(tuple(h))

            def __str__(self):
                return f' - <@{self.member_id}> {self.event_type.verb} ' \
                       f'{get_time_str(self.time, "R")}'

            # def _get_relative_time(self) -> str:
            #     currently = datetime.now(
            #         timezone.utc)  # The UTC Time to compare to
            #     if self.time.timestamp() == 0:
            #         return f' - <@{self.recipient_id}>: Unknown'
            #     else:
            #         seconds = int((currently - self.time).total_seconds())
            #         minutes = seconds // 60
            #         if seconds < 120:
            #             time_difference = f'{seconds} seconds'
            #         elif minutes < 120:
            #             time_difference = f'{minutes} minutes'
            #         else:
            #             time_difference = f'{minutes // 60} hours and' \
            #                               f' {minutes % 60} minutes'
            #         return f'{time_difference} ago'

        # def is_empty(self) -> bool:
        #     return self.member_count == 0

        # def _channel_event(self, event: VoiceEvent,
        #                    add_to: List[VoiceEvent],
        #                    remove_from: List[VoiceEvent]):
        #     """
        #     Updates lists of present and absent.
        #
        #     :param event: The VoiceEvent created by the event
        #     :param add_to: The list to append to
        #     :param remove_from: The list to remove from
        #     :return: None
        #     """
        #     add_to.append(event)
        #     for i, e in enumerate(remove_from):
        #         if event.recipient_id == e.recipient_id:
        #             remove_from.pop(i)
        #             break
        # for bundle in remove_from:
        #     if bundle.member_id == member_id:
        #         remove_from.pop(remove_from.index(bundle))
        #         break

        def event(self, member_id: int, event_type: VoiceStateChange,
                  executor_id: int = None):
            """
            Updates list if someone joined or left the VC

            Interface method for _event.
            :param member_id: The ID of the member being acted upon
            :param event_type: The type of the voice event
            :param executor_id: The ID of the member who caused the event
            :return: None
            """
            self._members.add(member_id)
            # executor_id = member_id if executor_id is None else executor_id
            event_log = self.VoiceEvent(member_id, event_type)
            self._full_log.append(event_log)
            # if event_type is VoiceStateChange.channel_join:
            # self._channel_event(event_log, self._present, self._absent)
            # self.member_count += 1
            # elif event_type is VoiceStateChange.channel_leave:
            # self._channel_event(event_log, self._absent, self._present)
            # self.member_count -= 1

        def log_iterator(self, event_types: Set[VoiceStateChange] = None,
                         include: Set[int] = None, exclude: Set[int] = None, *,
                         newest_first: bool = True, unique: bool = True) \
                -> Generator[VoiceEvent, None, None]:
            if include is None:
                include = self._members
            if exclude is not None:
                include = include.difference(exclude)
            if event_types is None:
                event_types = VoiceStateChange.__members__.values()

            iterator = self._full_log
            if newest_first:
                iterator = reversed(iterator)

            seen = set()
            for log_entry in iterator:
                if log_entry.event_type not in event_types or \
                        log_entry.member_id not in include:
                    continue
                if unique and log_entry not in seen:
                    yield log_entry
                    seen.add(log_entry)

        # def past_joined(self, member_id):
        #     """
        #     Updates list for people already in the VC from an unknown time
        #
        #     :param member_id: The ID of the Member
        #     :return: None
        #     """
        #     self._present.insert(0, self.VoiceEvent.unknown_time(member_id))
        #
        # def past_left(self, member_id):
        #     """
        #     Updates list for people who left the VC but were still in the log.
        #
        #     :param member_id: The ID of the Member
        #     :return: None
        #     """
        #     for bundle in self._present:
        #         if bundle.recipient_id == member_id:
        #             self._present.pop(self._present.index(bundle))

        # def refresh_channel(self, present_ids: Set[int]):
        #     for i, event in enumerate(self.present.copy()):
        #         if event.recipient_id not in present_ids:
        #             self._present.pop(i)
        #             self._absent.append(self.VoiceEvent(event.recipient_id,
        #                                 VoiceStateChange.refreshing))
        #     for i, event in enumerate(self._absent.copy()):
        #         if event.recipient_id in present_ids:
        #             self._absent.pop(i)
        #
        #     #Clear Duplicates
        #     if len(self._present) != len(set(self._present)):
        #         indexes = []
        #         for i, e in enumerate(self._present):
        #             for

        #
        # def get_bundle(self, member_id: int,
        #                present: bool = True) -> VoiceEvent:
        #     if present:
        #         return self._present[self._present.index(member_id)]
        #     return self._absent[self._absent.index(member_id)]

        # @property
        # def present(self) -> List[VoiceEvent]:
        #     """Gets the list of present members"""
        #     return self._present
        #
        # @property
        # def absent(self) -> List[VoiceEvent]:
        #     """Gets the list of members that have left"""
        #     return self._absent

    def __init__(self, bot: cmd.Bot):
        super().__init__(bot)
        self._logs = defaultdict(self._VcLogData)

    # def _event(self, channel_id: int, member_id: int,
    #            event_type: VoiceStateChange, executor_id: int = None):
    #     if event_type is VoiceStateChange.channel:
    #         self._logs[channel_id]

    def is_channel_empty(self, channel_id: int) -> bool:
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            raise ValueError
        return len(set(channel.voice_states)) == 0

    # @cmd.Cog.listener()
    # async def on_ready(self):
    #     # Checks for users already in a Voice Channel when Bot reconnects
    #     logger.info('Adding preexisting users in VC.')
    #     for guild in self.bot.guilds:
    #         for vc in guild.voice_channels:
    #             voices = set(vc.voice_states)
    #             if len(voices) == 0:
    #                 continue
    #             for log_entry in self._logs[vc.id].absent:
    #                 if log_entry.recipient_id in voices:

    #     known = set()
    #     if vc.id in self._logs:
    #         for bundle in self._logs[vc.id].present:
    #             known.add(bundle.recipient_id)
    #     for member_id in vc.voice_states:
    #         if member_id not in known:
    #             self._logs[vc.id].past_joined(member_id)
    # if vc.id in self._logs:
    #     for bundle in self._logs[vc.id].present:
    #         if bundle not in vc.voice_states:
    #             self._logs[vc.id].past_left(bundle.recipient_id)

    # @cmd.is_owner()
    # @cmd.command(hidden=True)
    # async def force_scan_vcs(self, ctx: cmd.Context):
    #     from main import invert_color
    #     message = await ctx.reply(embed=discord.Embed(
    #         title='Scanning VCs', color=invert_color(ctx.me.color)))
    #     await self.on_ready()
    #     await message.edit(embed=discord.Embed(
    #         title='Scanned VCs', color=invert_color(ctx.me.color)))

    @cmd.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    old_state: discord.VoiceState,
                                    new_state: discord.VoiceState):
        """
        Trigger to update list if someone joined or left VC

        :param member: The member that triggered the voice state update
        :param old_state: The Voice State before the voice state update
        :param new_state: The Voice State after the voice state update
        :return: None
        """
        if old_state.channel != new_state.channel:
            # if old_state.afk != new_state.afk:
            #     pass
            self._moved(member, old_state.channel, new_state.channel,
                        old_state.afk, new_state.afk)

        # elif before.deaf != after.deaf:
        #     pass
        # elif before.mute != after.mute:
        #     pass
        # elif before.self_deaf != after.self_deaf:
        #     pass
        # elif before.self_mute != after.self_mute:
        #     pass
        # elif before.self_stream != after.self_stream:
        #     pass
        # elif before.self_video != after.self_video:
        #     pass
        # elif before.suppress != after.suppress:
        #     pass
        # elif before.requested_to_speak_at != after.requested_to_speak_at:
        #     pass

        # # Rules out voice state updates that aren't join/leave
        # if before.channel == after.channel:
        #     logger.debug('Voice State Update: Ignored')
        #     return

    def _moved(self, member: discord.Member,
               old_channel: Union[
                   discord.VoiceChannel, discord.StageChannel],
               new_channel: Union[
                   discord.VoiceChannel, discord.StageChannel],
               old_afk: bool = False, new_afk: bool = False):

        if old_channel is not None:
            self._logs[old_channel.id].event(
                member.id, VoiceStateChange.channel_leave)
            if self.is_channel_empty(old_channel.id):
                del self._logs[old_channel.id]

        if new_channel is not None:
            self._logs[new_channel.id].event(
                member.id, VoiceStateChange.channel_join)

    # logs = discord.commands.SlashCommandGroup("logs",
    #                                           "show voice channel logs")

    # logs = discord.SlashCommandGroup('logs', 'foo')
    # logs.hidden = False

    log_command_group = discord.SlashCommandGroup("vclog", "foo")

    @log_command_group.command()
    async def joined(self, ctx: discord.ApplicationContext, *,
                     channel: Optional[discord.VoiceChannel],
                     amount: int = -1):
        # async def joined(self, ctx: discord.ApplicationContext):
        """Shows who have joined your VC and how long ago."""
        await ctx.defer()
        await ctx.respond(
            embed=self._vc_log_embed(ctx, VoiceStateChange.channel_join,
                                     amount, channel=channel))

    @log_command_group.command()
    async def left(self, ctx: discord.ApplicationContext, *,
                   channel: Optional[discord.VoiceChannel],
                   amount: int = -1):
        # async def left(self, ctx: discord.ApplicationContext):
        """Shows who have left your VC and how long ago."""
        await ctx.defer()
        await ctx.respond(
            embed=self._vc_log_embed(ctx, VoiceStateChange.channel_leave,
                                     amount, None, channel=channel))

    def _vc_log_embed(self, ctx: discord.ApplicationContext,
                      vsc_type: VoiceStateChange,
                      amount: int = -1, only_present: Optional[bool] = True,
                      channel: Optional[discord.VoiceChannel] = None) \
            -> discord.Embed:
        """Creates an embed with for the VC Log"""
        # Filter for if command caller is not in a voice chat
        if channel is None \
                and not isinstance(ctx.channel, discord.VoiceChannel) \
                and ctx.author.voice is None:
            logger.debug('VC Embed not made, user not in a VC')
            return discord.Embed(
                title='Could not fetch VC Log',
                description='You\'re not in a Voice Channel.',
                color=self.error_color)

        if isinstance(ctx.channel, discord.VoiceChannel):
            vc = ctx.channel
        else:
            vc = channel or ctx.author.voice.channel
        if not isinstance(vc, discord.VoiceChannel): raise ValueError(type(vc))
        voices = set(vc.voice_states)
        if only_present:
            options = {'include': set(m.id for m in vc.members)}
        elif only_present is None:
            options = {'exclude': set(m.id for m in vc.members)}
        else:
            options = {}
        bundles = self._logs[vc.id].log_iterator({vsc_type}, **options)
        if amount > -1:
            iterator = (e for i, e in zip(range(amount), bundles))
        else:
            iterator = bundles

        # Set up variables for embed formatting

        title = f'{vsc_type.name.replace("_", " ").capitalize()}' \
                f' history in `{vc.name}` :'
        desc = ''
        for bundle in iterator:
            desc += f'{bundle}\n'
            if vsc_type == VoiceStateChange.channel_join:
                voices.remove(bundle.member_id)
        else:
            if vsc_type == VoiceStateChange.channel_join and len(voices) != 0 \
                    and amount < 0:
                for voice_id in voices:
                    desc += f'- <@{voice_id}> joined channel `sometime`\n'

        return discord.Embed(title=title,
                             description=desc if desc else ' - None',
                             color=vc.guild.me.color)
