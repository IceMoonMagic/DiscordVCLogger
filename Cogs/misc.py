"""Cog of random commands that don't fit elsewhere."""
import logging
import random as r
from asyncio import sleep

import discord
import discord.ext.commands as cmd

from .cog_manager import Cog

logger = logging.getLogger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info('Loading Cog: Misc')
    bot.add_cog(Misc(bot))


class Misc(Cog):
    """Random Commands that don't fit anywhere else"""

    def __init__(self, bot: cmd.Bot):
        super().__init__(bot)
        self.ride_members = {}
        self._shutdown = False

    def shutdown(self):
        self._shutdown = True

    def shutdown_complete(self) -> bool:
        return len(self.ride_members) == 0

    @cmd.command()
    @cmd.bot_has_guild_permissions(move_members=True)
    async def ride(self, ctx: cmd.Context, times: int = 5):
        """
        Take a ride around the VCs in your current category.

        :param ctx: Discord's context parameter.
        :param times: How many times to be moved.
        """
        if ctx.author.id in self.ride_members:
            return
        if ctx.author.voice is None:
            await ctx.send(embed=discord.Embed(
                title='You\'re not in a Voice Channel.',
                color=self.error_color))
            return

        # Get Valid Voice Channels
        before_state = ctx.author.voice
        start_channel = current_channel = ctx.author.voice.channel
        channels = []
        for c in start_channel.category.voice_channels:
            if c.permissions_for(ctx.author).connect:
                channels.append(c)
        channels.pop(channels.index(start_channel))

        # Aborts if there is not enough VCs in the category that the member can
        # connect to
        if len(channels) == 0:
            await ctx.send(embed=discord.Embed(
                title='No other Voice Channels found.',
                description='You must be allowed to connect to at least two '
                            'voice channels in the category.',
                color=self.error_color))
            return

        logger.info(f'Starting Ride for'
                    f' {ctx.author.id} ({ctx.author.display_name})'
                    f' in {ctx.guild.id} ({ctx.guild.name})'
                    f' in {start_channel.category.id}'
                    f' ({start_channel.category.name})')
        # Let other cogs know to ignore this member's movements
        for i in self.ride_set_ignore:
            self.bot.get_cog(i).ignore.add(ctx.author.id)
        self.ride_members.add(ctx.author.id)

        def create_embed(moved: int, finished: bool = False) -> discord.Embed:
            """Creates the embed for the ride"""
            # return discord.Embed(
            #     title='Enjoy the Ride').add_field(
            #     name='Times Moved', value=f'{moved}').add_field(
            #     name='Requested Moves', value=times).add_field(
            #     name='Remaining Moves',
            #     value=f'{times - moved}' if not finished else '0')
            if not finished:
                desc = f'{times - moved} moves remaining.'
            else:
                desc = 'Finished Moving.'
            return discord.Embed(
                title='Enjoy the Ride',
                description=f'Moved {moved} times'
                            f' of requested {times}.\n{desc}',
                footer='Disconnect to end early.',
                color=ctx.guild.me.color)

        # Ride, HTTPException expected if user disconnects
        message = await ctx.send(content=f'{ctx.author.mention}',
                                 embed=create_embed(0))
        move = 0
        for move in range(times):
            if self._shutdown:
                break
            new_channel = channels.pop(r.randint(0, len(channels) - 1))
            channels.append(current_channel)
            try:
                await ctx.author.move_to(new_channel)
                await message.edit(embed=create_embed(move + 1))
            except discord.HTTPException:
                break
            current_channel = new_channel
            await sleep(0.5)

        # Restore original state
        # ToDo: Need to remove cog's ignore before sending update
        try:
            await ctx.author.edit(voice_channel=start_channel)
        except discord.HTTPException:
            # Makes Cogs told to ignore recognise the member's disconnect
            for i in self.ride_set_ignore:
                after_state = before_state
                after_state.channel = None
                await self.bot.get_cog(i).on_voice_state_update(
                    ctx.author, before_state, after_state)
        await message.edit(embed=create_embed(move+1, True))
        self.ride_members.remove(ctx.author.id)
        for i in self.ride_set_ignore:
            self.bot.get_cog(i).ignore.remove(ctx.author.id)
