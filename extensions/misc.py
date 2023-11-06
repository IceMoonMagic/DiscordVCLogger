import discord
import discord.ext.commands as cmds

import database as db
import utils

logger = db.get_logger(__name__)


def setup(bot: cmds.Bot):
    """Adds the cog to the bot"""
    logger.info(f"Loading Cog: Misc")
    bot.add_cog(MiscCommands())


def teardown(bot: cmds.Bot):
    """Removes the cog from the bot"""
    logger.info(f"Unloading Cog: Misc")
    bot.remove_cog(f"{MiscCommands.qualified_name}")


class MiscCommands(cmds.Cog):
    link_fixes: dict = db.get_json_data(__name__).get("link fixes", {})

    @discord.message_command(name="Convert Links")
    async def fix_links(
        self, ctx: discord.ApplicationContext, message: discord.Message
    ):
        # await ctx.defer()
        new_text = message.content
        for old, new in self.link_fixes.items():
            new_text = new_text.replace(old, new)
        if new_text != message.content:
            await ctx.respond(new_text)
        else:
            await ctx.respond(
                embed=utils.make_error("No links to fix." f"`{new_text}`"),
                ephemeral=True,
            )

    @discord.user_command(name="Get Avatar")
    async def get_avatar(
        self,
        ctx: discord.ApplicationContext,
        user: discord.User | discord.Member,
    ):
        embeds: list[discord.Embed] = [
            utils.make_embed(
                title=f"Avatar", desc=user.mention, color=user.color
            ).set_image(url=user.display_avatar.url)
        ]

        if isinstance(user, discord.Member) and user.guild_avatar:
            embeds[0].title = f"Local Avatar"
            embeds.insert(
                0,
                utils.make_embed(
                    title=f"Global Avatar",
                    desc=user.mention,
                    color=user.accent_color,
                ).set_image(url=user.avatar.url),
            )

        await ctx.respond(embeds=embeds)
