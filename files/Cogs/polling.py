""""""
import logging
from typing import List
import discord
import discord.ext.commands as cmd
import dataclasses as dc


logger = logging.getLogger(__name__)


def setup(bot: cmd.Bot):
    """Adds the cog to the bot"""
    logger.info('Loading Cog: Polling')
    bot.add_cog(polling(bot))


class polling(cmd.Cog):
    """"""

    @dc.dataclass()
    class _poll:
        """"""

        message_id: int
        style: str
        prompt: str
        choices: List[str]
        reactions: List[str]
        votes: dc.field(default_factory=dict, init=False)
        closed: dc.field(default=False, init=False)

        def __post_init__(self):
            styles = ['normal', 'ranked', 'multiple choice', 'n', 'r', 'mc']
            if not self.style.islower():
                self.style = self.style.lower()
            # Checks if style is recognized
            if self.style not in styles:
                raise ValueError(f'Invalid style value. Expected: {styles} | '
                                 f'Got {self.style}')
            # Changes self.style to shorter version if needed
            elif self.style in styles[:3]:
                self.style = styles[styles.index(self.style) + 3]
            # Ensures self.choices and self.reactions have the same length
            if len(self.choices) != len(self.reactions):
                raise ValueError(f'Length of choices and reactions do not match'
                                 f'. choices: {len(self.choices)}, reactions: '
                                 f'{len(self.reactions)}')

        def


# Styles: Standard, Ranked, Multiple Choice


    def __init__(self, bot: cmd.Bot):
        self.bot = bot
        self.polls = {}
