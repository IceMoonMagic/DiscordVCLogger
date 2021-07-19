import logging
import re  # https://docs.python.org/3/library/re.html

import discord
import discord.ext.commands as cmd

from .cog_manager import Cog

logger = logging.getLogger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info('Loading Cog: Dumb')
    bot.add_cog(Dumb(bot))


class Dumb(Cog):
    """For random and dumb things for the bot to do."""

    def __init__(self, bot):
        super().__init__(bot)
        self.deafened = set()
        self.muted = set()

    @cmd.Cog.listener(name='on_message')
    @cmd.bot_has_guild_permissions(manage_nicknames=True)
    async def im_nickname(self, message: discord.Message):
        """Changes the member's nickname if their message starts with 'I am'"""
        if message.author == self.bot:
            return

        NICK_MAX = 32
        i_am = {'i am', 'i\'m', 'im'}
        regexed = '|'.join([f'(?<=(?<!\S){i}\s)' for i in i_am])
        nick = re.search(f'(?:{regexed}).{{,{NICK_MAX}}}(?=\s|$)',
                         message.content, flags=re.IGNORECASE)
        if nick is None:
            return
        else:
            nick = nick.group()
        logger.info(f'Changing nickname of {message.author.mention} to {nick}.')
        try:
            await message.author.edit(nick=nick)
        except discord.HTTPException:
            logger.info(f'Name change failed.')

    @cmd.command()
    @cmd.bot_has_guild_permissions(deafen_members=True)
    async def deafen(self, ctx: cmd.Context):
        """Allows you to server deafen yourself."""
        if ctx.author.voice is None:
            await self._send_error(ctx, desc='Command only usable when '
                                             'in a Voice Channel')
        elif not ctx.author.voice.deaf:
            self.deafened.add(ctx.author.id)
            await ctx.author.edit(deafen=True)
        elif ctx.author.id in self.deafened:
            self.deafened.remove(ctx.author.id)
            await ctx.author.edit(deafen=False)
        else:
            await self._send_error(ctx, 'Will Not Un-Deafen',
                                   'Can only be used to un-server-deafen if '
                                   'the command caused the server deafen.')

    @cmd.command()
    @cmd.bot_has_guild_permissions(mute_members=True)
    async def mute(self, ctx: cmd.Context):
        """Allows you to server mute yourself."""
        if ctx.author.voice is None:
            await self._send_error(ctx, desc='Command only usable when '
                                             'in a Voice Channel')
        elif not ctx.author.voice.mute:
            self.muted.add(ctx.author.id)
            await ctx.author.edit(mute=True)
        elif ctx.author.id in self.muted:
            self.muted.remove(ctx.author.id)
            await ctx.author.edit(mute=False)
        else:
            await self._send_error(ctx, 'Will Not Un-Mute',
                                   'Can only be used to un-server-mute if '
                                   'the command caused the server mute.')

    @cmd.Cog.listener(name='on_voice_state_update')
    async def _un_deafen_mute(self, member: discord.Member,
                              before: discord.VoiceState,
                              after: discord.VoiceState):
        """Removes members from sets if un deafened/muted by someone else."""
        if before.deaf and not after.deaf:
            if member.id in self.deafened:
                self.deafened.remove(member.id)
        if before.mute and not after.mute:
            if member.id in self.muted:
                self.muted.remove(member.id)
