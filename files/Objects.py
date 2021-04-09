"""Obsolete"""
import dataclasses as dc
import datetime as dt

import discord
import typing as t
import saving


@dc.dataclass(order=True)
class GuildData:
    _guild_id: int
    _settings: dict = dc.field(default_factory=dict, compare=False, init=False)
    _vc_log: dict = dc.field(default_factory=dict, compare=False, init=False)
    _notifications: dict = dc.field(default_factory=dict, compare=False,
                                    init=False)

    guild_prefixes = {}

    @classmethod
    def get_guild_prefix(cls, guild_id):
        if guild_id not in cls.guild_prefixes:
            cls(guild_id)
        return cls.guild_prefixes[guild_id]

    def __post_init__(self):
        # self.guilds[self.guild_id] = self
        self._settings['prefix'] = '|'
        self._settings['delete_bookmark'] = True
        saved = saving.load_guild(self._guild_id)
        if saved is not None:
            self.__setstate__(saved)
        for n in self._notifications:
            self._notifications[n] = self._ChannelNotifications()
        self.guild_prefixes[self._guild_id] = self.prefix

    def __del__(self):
        saving.save_guild(self._guild_id, self.__getstate__())

    def __getstate__(self) -> dict:
        d = {'guild_id': self._guild_id, 'settings': self._settings,
             'notifications': {}, 'vc_log': {}}
        for n in self._notifications:
            d['notifications'][n] = list(self._notifications[n].__getstate__())
        for v in self._vc_log:
            d['vc_log'][v] = self._vc_log[v].__getstate__()
        return d

    def __setstate__(self, d: dict):
        self._settings = d['settings']
        for n in d['notifications']:
            members = set()
            for m in d['notifications'][n]:
                members.add(int(m))
            self._notifications[
                int(n)] = self._ChannelNotifications.__setstate__(members)
        self._vc_log = {}
        for v in d['vc_log']:
            self._vc_log[int(v)] = self._ChannelConnections(**d['vc_log'][v])

    def vc_event(self, channel: discord.VoiceChannel, member: discord.Member,
                 joined: bool):
        channel_id = channel.id
        if channel_id not in self._vc_log:
            self._vc_log[channel_id] = self._ChannelConnections()
        if joined:
            self._vc_log[channel_id].joined(member.id)
        else:
            if len(self._vc_log[channel_id].present) is not 0:
                self._vc_log[channel_id].left(member.id)
            else:
                del self._vc_log[channel_id]

    @property
    def guild_id(self):
        return self._guild_id

    @property
    def vc_log(self):
        return self._vc_log

    @property
    def prefix(self):
        return self._settings['prefix']

    @prefix.setter
    def prefix(self, new_prefix: str):
        self._settings['prefix'] = new_prefix
        self.guild_prefixes[self._guild_id] = new_prefix

    @property
    def book_del(self):
        return self._settings['delete_bookmark']

    @book_del.setter
    def book_del(self, to: bool):
        self._settings['delete_bookmark'] = to

    @dc.dataclass()
    class _ChannelConnections:
        _present: list = dc.field(default_factory=list)
        _absent: list = dc.field(default_factory=list)

        def __getstate__(self) -> dict:
            return {'_present': self._present, '_absent': self._absent}

        @staticmethod
        def bundle(member_id: int) -> dict:
            return {'member_id': member_id,
                    'time': dt.datetime.utcnow().timestamp()}

        @staticmethod
        def member_in(member_id: int, within: list) -> int:
            for bundle in within:
                if bundle['member_id'] == member_id:
                    return within.index(bundle)
            return -1

        def _event(self, member_id: int, add: list, remove: list):
            data = self.bundle(member_id)
            at = self.member_in(member_id, remove)
            if at > -1:
                remove.pop(at)
            add.append(data)

        def joined(self, member_id: int):
            self._event(member_id, self._present, self._absent)

        def left(self, member_id: int):
            self._event(member_id, self._absent, self._present)

        @property
        def present(self):
            return self._present

        @property
        def absent(self):
            return self._absent

    @dc.dataclass
    class _ChannelNotifications:
        _listeners: dict = dc.field(default_factory=dict, init=False)
        _participants: dict = dc.field(default_factory=dict, init=False)
        _key_messages: list = dc.field(default_factory=dict, init=False)

        jump_url = type(discord.Message.jump_url)

        def add_listener(self, user_id):
            self._listeners[user_id] = None

        def remove_listener(self, user_id):
            del self._listeners[user_id]

        def new_message(self, author_id: int, jump: jump_url):
            if author_id in self._participants:
                self._participants[author_id] += 1
            else:
                self._participants[author_id] = 1
            if not self.currently_conversation:
                self._key_messages[0] = jump
            self._key_messages[1] = jump

        def done(self):
            listeners = self._listeners
            self.__init__()
            self._listeners = dict.fromkeys(listeners)

        def __post_init__(self):
            self._key_messages = [None, None]

        def __getstate__(self) -> set:
            return set(self._listeners.keys())

        @classmethod
        def __setstate__(cls, listeners: set):
            o = cls()
            o._listeners = dict.fromkeys(listeners)
            return o

        @property
        def listeners(self) -> dict:
            return self._listeners

        @property
        def participants(self) -> dict:
            return self._participants

        @property
        def first_message(self) -> discord.Message.jump_url:
            return self._key_messages[0]

        @property
        def latest_message(self) -> discord.Message.jump_url:
            return self._key_messages[1]

        @property
        def currently_conversation(self) -> bool:
            return self._key_messages[0] is not None


#
# @dc.dataclass(order=True)
# class UserData:
#     _background: t.Optional[str] = dc.field(default=None, init=False)
#     _bgStyle: int = dc.field(default=0, init=False)
#     _birthday: t.Optional[dt.datetime] = dc.field(default=None, init=False)
#     _gender: str = dc.field(default='Not Specified', init=False)
#     _pronouns: str = dc.field(default='Not Specified', init=False)
#     _desc: str = dc.field(default='', init=False)
#     _user_id: int
#
#     avail_genders = {'M': 'Male',
#                      'F': 'Female',
#                      'O': 'Other',
#                      'N': 'Not Specified'}
#     avail_pronouns = {'H': 'He / Him / His',
#                       'S': 'She / Her / Hers',
#                       'Z': 'Ze / Zir / Zirs',
#                       'T': 'They / Them / Their',
#                       'N': 'Not Specified'}
#
#     def __post_init__(self):
#         saved = Saving.load_user(self._user_id)
#         if saved is not None:
#             self.__setstate__(saved)
#
#     def __del__(self):
#         Saving.save_user(self._user_id, self.__getstate__())
#
#     def __getstate__(self) -> dict:
#         birthday = self._birthday.timestamp() if self._birthday else None
#         return {'birthday': birthday, 'id': self._user_id,
#                 'gender': self._gender, 'pronouns': self._pronouns,
#                 'background': self._background, 'desc': self._desc}
#
#     def __setstate__(self, d: dict):
#         if d['birthday'] is not None:
#             self._birthday = dt.datetime.utcfromtimestamp(d['birthday'])
#         self._user_id = d['id']
#         self._gender = d['gender']
#         self._pronouns = d['pronouns']
#         self._background = d['background']
#         self._desc = d['desc']
#
#     @property
#     def id(self):
#         return self._user_id
#
#     @property
#     def background(self):
#         return self._background
#
#     @background.setter
#     def background(self, link: str):
#         self._background = link
#
#     @property
#     def birthday(self):
#         return self._birthday
#
#     @birthday.setter
#     def birthday(self, date: t.Optional[dt.datetime]):
#         if date is None:
#             self._birthday = None
#         elif date > dt.datetime.now(dt.timezone.utc):
#             raise ValueError('Can\'t be born in the future.')
#         else:
#             self._birthday = date
#
#     @property
#     def gender(self):
#         return self._gender
#
#     @gender.setter
#     def gender(self, g: str):
#         if g not in self.avail_genders:
#             raise ValueError
#         self._gender = self.avail_genders[g]
#
#     @property
#     def pronouns(self):
#         return self._pronouns
#
#     @pronouns.setter
#     def pronouns(self, p: str):
#         p = p.strip().upper()
#         if p not in self.avail_pronouns:
#             raise ValueError
#         self._pronouns = self.avail_pronouns[p]
