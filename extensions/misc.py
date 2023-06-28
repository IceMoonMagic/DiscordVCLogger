import discord
import discord.ext.commands as cmds

import database as db
import system

logger = db.get_logger(__name__)


def setup(bot: cmds.Bot):
    """Adds the cog to the bot"""
    logger.info(f'Loading Cog: Misc')
    bot.add_cog(MiscCommands())


def teardown(bot: cmds.Bot):
    """Removes the cog from the bot"""
    logger.info(f'Unloading Cog: Misc')
    bot.remove_cog(f'{MiscCommands.qualified_name}')


class MiscCommands(cmds.Cog):

    link_fixes: dict = db.get_json_data().get('link_fixes', {})

    @discord.message_command(name='Convert Links')
    async def fix_links(
            self,
            ctx: discord.ApplicationContext,
            message: discord.Message):
        # await ctx.defer()
        new_text = message.content
        for old, new in self.link_fixes.items():
            new_text = new_text.replace(old, new)
        if new_text != message.content:
            await ctx.respond(new_text)
        else:
            await ctx.followup.send(
                embed=system.make_error('No links to fix.' f'`{new_text}`'),
                ephemeral=True
            )
