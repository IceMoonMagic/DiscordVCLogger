"""Code to let a bot to track joins and disconnects of Discord voice channels"""

import dataclasses as dc
import datetime as dt
import logging

import discord
import discord.ext.commands as cmd

logger = logging.getLogger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info('Loading Cog: VC Log')
    bot.add_cog(VcLog(bot))


class VcLog(cmd.Cog):
    """Cog for monitoring who joined and left a VC"""

    @dc.dataclass()
    class _VcLogData:
        """Stores the data for a VC"""

        _present: list = dc.field(default_factory=list, init=False)
        _absent: list = dc.field(default_factory=list, init=False)

        @dc.dataclass(frozen=True)
        class _VoiceEvent:
            """Bundles the Member and Time of a Voice Event"""
            member_id: int
            time: dt.datetime = dc.field(
                default_factory=lambda: dt.datetime.now(dt.timezone.utc))

        def _event(self, member_id: int, add_to: list, remove_from: list):
            """
            Updates lists of present and absent.

            :param member_id: The ID of the Member
            :param add_to: The list to append to
            :param remove_from: The list to remove from
            :return: None
            """
            add_to.append(self._VoiceEvent(member_id))
            for bundle in remove_from:
                if bundle.member_id == member_id:
                    remove_from.pop(remove_from.index(bundle))
                    break

        def event(self, member_id: int, joined: bool):
            """
            Updates list if someone joined or left the VC

            Interface method for _event.
            :param member_id: The ID of the Member
            :param joined: True if the member joined the channel, False if left
            :return: None
            """
            if joined:
                self._event(member_id, self._present, self._absent)
            else:
                self._event(member_id, self._absent, self._present)

        def past_joined(self, member_id):
            """
            Updates list for people already in the VC from an unknown time

            :param member_id: The ID of the Member
            :return: None
            """
            self._present.insert(0, self._VoiceEvent(
                member_id, time=dt.datetime.fromtimestamp(
                    0, tz=dt.timezone.utc)))

        def past_left(self, member_id):
            """
            Updates list for people who left the VC but were still in the log.

            :param member_id: The ID of the Member
            :return: None
            """
            for bundle in self._present:
                if bundle.member_id == member_id:
                    self._present.pop(self._present.index(bundle))

        @property
        def present(self):
            """Gets the list of present members"""
            return self._present

        @property
        def absent(self):
            """Gets the list of members that have left"""
            return self._absent

    def __init__(self, bot: cmd.Bot):
        self.bot = bot
        if hasattr(bot, 'error_color'):
            self.error_color = bot.error_color
        else:
            self.error_color = discord.Color.dark_red()
        self.ignore = set()  # Set of users to ignore
        self._logs = {}

    @cmd.Cog.listener()
    async def on_ready(self):
        # Checks for users already in a Voice Channel when Bot reconnects
        logger.info('Adding preexisting users in VC.')
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                if len(vc.voice_states) != 0:
                    if vc.id not in self._logs:
                        self._logs[vc.id] = self._VcLogData()
                        known = set()
                    else:
                        known = set()
                        for bundle in self._logs[vc.id].present:
                            known.add(bundle.member_id)
                    for member_id in vc.voice_states:
                        if member_id not in known:
                            self._logs[vc.id].past_joined(member_id)
                if vc.id in self._logs:
                    for bundle in self._logs[vc.id].present:
                        if bundle.member_id not in vc.voice_states:
                            self._logs[vc.id].past_left(bundle.member_id)


    @cmd.is_owner()
    @cmd.command(hidden=True)
    async def force_scan_vcs(self, ctx: cmd.Context):
        from main import invert_color
        message = await ctx.send(embed=discord.Embed(
            title='Scanning VCs', color=invert_color(ctx.me.color)))
        await self.on_ready()
        await message.edit(embed=discord.Embed(
            title='Scanned VCs', color=invert_color(ctx.me.color)))

    @cmd.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        """
        Trigger to update list if someone joined or left VC

        :param member: The member that triggered the voice state update
        :param before: The Voice State before the voice state update
        :param after: The Voice State after the voice state update
        :return: None
        """
        # Rules out voice state updates that aren't join/leave
        if before.channel == after.channel or member.id in self.ignore:
            logger.debug('Voice State Update: Ignored')
            return
        logger.info(f'Voice State Update: {member.id} ({member.display_name})'
                    f' in {member.guild.id} ({member.guild.name}).')
        # If member was in a channel before voice state update
        if before.channel is not None:
            self._logs[before.channel.id].event(member.id, False)
            if len(self._logs[before.channel.id].present) == 0:
                # Deletes the _VcLogData if associated channel is empty
                logger.info(f'{before.channel.id} ({before.channel.name}) is'
                            f' empty, deleting logs.')
                del self._logs[before.channel.id]

        # If member ended in a channel after voice state update
        if after.channel is not None:
            if after.channel.id not in self._logs:
                # Creates a _VcLogData if there is not one associated
                # with the channel yet
                logger.info(f'{after.channel.id} ({after.channel.name}) has no'
                            f' logs, creating.')
                self._logs[after.channel.id] = self._VcLogData()
            self._logs[after.channel.id].event(member.id, True)

    @cmd.command()
    async def joined(self, ctx: cmd.Context, amount: int = -1):
        """Shows who has joined your VC and how long ago."""
        await ctx.send(embed=self._vc_log_embed(ctx, True, amount))

    @cmd.command()
    async def left(self, ctx: cmd.Context, amount: int = -1):
        """Shows who has left your VC and how long ago."""
        await ctx.send(embed=self._vc_log_embed(ctx, False, amount))

    def _vc_log_embed(self, ctx: cmd.Context, joined: bool, amount: int = -1) \
            -> discord.Embed:
        """Creates an embed with for the VC Log"""
        # Filter for if command caller is not in a voice chat
        if ctx.author.voice is None:
            logger.debug('VC Embed not made, user not in a VC')
            return discord.Embed(
                title='Could not fetch VC Log',
                description='You\'re not in a Voice Channel.',
                color=self.error_color)

        logger.info(f'Creating VC Log Embed for {ctx.author.voice.channel.id}'
                    f'({ctx.author.voice.channel.name})')
        # Gets the list of Members/Times to use
        bundles = self._logs[ctx.author.voice.channel.id]
        bundles = bundles.present if joined else bundles.absent
        if amount <= -1:
            amount = len(bundles)

        # Set up variables for embed formatting
        title = f'{"Join" if joined else "Leave"} history in' \
                f' __{ctx.author.voice.channel.name}__:'
        desc = ''
        currently = dt.datetime.now(dt.timezone.utc)  # The UTC Time to compare to
        for bundle, _ in zip(reversed(bundles), range(amount)):
            if bundle.time.timestamp() == 0:
                desc += f' - <@{bundle.member_id}>: Unknown\n'
            else:
                seconds = int((currently - bundle.time).total_seconds())
                minutes = seconds // 60
                if seconds < 120:  # Only shows seconds if less than 2 Minutes
                    time_difference = f'{seconds} seconds'
                elif minutes < 120:  # Only shows minutes if less than 2 Hours
                    time_difference = f'{minutes} minutes'
                else:  # Shows Hours and Minutes otherwise
                    time_difference = f'{minutes // 60} hours and' \
                                      f' {minutes % 60} minutes'
                # Adds line in format " - [Mention Member]: [Time] ago"
                desc += f' - <@{bundle.member_id}>: {time_difference} ago\n'

        embed = discord.Embed(title=title,
                              description=desc if desc else ' - None',
                              color=ctx.guild.me.color)
        return embed
