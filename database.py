import asyncio
import datetime as dt
import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import AsyncGenerator, Generic, Iterable, TypeVar

import aiosqlite as sql
import nacl.secret


def setup_logging(to_stdout: bool = True,
                  local_level: int = logging.INFO,
                  root_level: int = logging.WARNING):
    logging.Formatter.converter = time.gmtime

    now = dt.datetime.utcnow().astimezone(dt.timezone.utc)
    error_handler = RotatingFileHandler(
        f'logs/{now.strftime("%Y-%m-%dT%H%M+00")}.log',
        maxBytes=524288,
        backupCount=3)
    file_handler = RotatingFileHandler(
        f'logs/{now.strftime(LOG_NAME)}.log',
        maxBytes=524288,
        backupCount=3)
    console_handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter(
        '{asctime}|{levelname}|{lineno}|{name}|{message}',
        '%Y-%m-%d %H:%M:%S', "{")

    error_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    _logger = logging.getLogger(LOG_NAME)
    _logger.setLevel(local_level)

    _logger.addHandler(file_handler)
    if to_stdout:
        _logger.addHandler(console_handler)

    error_handler.setLevel(logging.WARNING)
    logging.getLogger().setLevel(root_level)
    logging.getLogger().addHandler(error_handler)


def get_logger(name) -> logging.Logger:
    return logging.getLogger(f'{LOG_NAME}.{name}')


def get_json_data() -> dict:
    with open(JSON_PATH) as file:
        return json.load(file)


JSON_PATH = r'saves/bot_key.json'

LOG_NAME = 'discord_bot'
logger = get_logger(__name__)

DB_FILE = r'saves/database.db'
SQL_CAST = {bool: 'bool', int: 'int', str: 'nvarchar'}

S = TypeVar("S", bound='Storable')


class Storable:
    table_name = 'Storable'
    primary_key_name = 'table_name'

    encrypt_attrs: list = []
    box: nacl.secret.SecretBox | None = None

    def __init_subclass__(cls: type[S], **kwargs):
        if cls.table_name == super(cls, cls).table_name:
            cls.table_name = cls.__name__

        if cls.primary_key_name not in cls.__annotations__:
            raise AttributeError(f'{cls.__class__} has no annotation '
                                 f'{cls.primary_key_name}. Available: '
                                 f'{list[cls.__annotations__]}')
        if cls.primary_key_name in cls.encrypt_attrs:
            raise AttributeError(
                f'primary_key_name ({cls.primary_key_name}) '
                f'may not be encrypted.')
        super().__init_subclass__()

    def __post_init__(self: S) -> S:
        for attr, type_ in self.__annotations__.items():
            if not isinstance(value := getattr(self, attr), type_):
                setattr(self, attr, type_(value))
        return self

    def copy(self: S) -> S:
        attributes = {}
        for attribute in self.__annotations__:
            attributes[attribute] = getattr(self, attribute)
        return self.__class__(**attributes)

    def update(self: S, *,
               update_inplace: bool = True,
               **kwargs) -> S:
        work_on: S = self if update_inplace else self.copy()
        for kw, arg in kwargs.items():
            setattr(work_on, kw, arg)
        return work_on.__post_init__()

    async def save(self: S):
        if not self.is_ready():
            raise MissingEncryptionKey(self.__class__)

        encrypted = {}
        unique_chars: int = len(str(len(self.encrypt_attrs)))
        primary_value = f'{getattr(self, self.primary_key_name)}'
        nonce_base = f'{primary_value[:24 - unique_chars]:0{24 - unique_chars}}'
        for i, attr in enumerate(self.encrypt_attrs):
            nonce = f'{i:0{unique_chars}}{nonce_base}'.encode()

            raw_value: str = getattr(self, attr)
            bytes_value = raw_value.encode()
            encrypted_value = self.box.encrypt(bytes_value, nonce).ciphertext
            encrypted[attr] = encrypted_value.hex()

        await save_data(self.update(update_inplace=False, **encrypted))

    def decrypt(self: S, decrypt_inplace: bool = True) -> S:
        work_on: S = self if decrypt_inplace else self.copy()

        if not work_on.is_ready():
            raise MissingEncryptionKey(self.__class__)

        unique_chars: int = len(str(len(work_on.encrypt_attrs)))
        primary_value = f'{getattr(work_on, work_on.primary_key_name)}'
        nonce_base = f'{primary_value[:24 - unique_chars]:0{24 - unique_chars}}'
        for i, attr in enumerate(work_on.encrypt_attrs):
            nonce = f'{i:0{unique_chars}}{nonce_base}'.encode()

            hex_value: str = getattr(work_on, attr)
            bytes_value = bytes.fromhex(hex_value)
            decrypted_value = work_on.box.decrypt(bytes_value, nonce)
            # decrypted[attr]: str = decrypted_value.decode()
            setattr(work_on, attr, decrypted_value.decode())

        return work_on

    @classmethod
    async def load(cls: type[S], primary_key, decrypt: bool = True) \
            -> S | None:
        where = f'{cls.primary_key_name} = {primary_key}'
        try:
            obj = await anext(cls.load_gen(where=where, decrypt=decrypt))
        except StopAsyncIteration:
            return None

        return obj

    @classmethod
    async def load_all(cls: type[S], decrypt: bool = True, **where) -> list[S]:
        return await load_data_all(cls, decrypt=decrypt, **where)

    @classmethod
    def load_gen(cls: type[S], decrypt: bool = True, **where) \
            -> AsyncGenerator[S, None]:
        return load_data_gen(cls, decrypt=decrypt, **where)

    @classmethod
    async def delete(cls, primary_key):
        where = f'{cls.primary_key_name} = {primary_key}'
        await cls.delete_all(where=where)

    @classmethod
    async def delete_all(cls, **where):
        await delete(cls, **where)

    @classmethod
    def is_ready(cls) -> bool:
        return len(cls.encrypt_attrs) == 0 or cls.box is not None

    @classmethod
    def set_key(cls, key: str | bytes):
        if isinstance(key, str):
            key = key.encode()
        cls.box = nacl.secret.SecretBox(key)

    @classmethod
    def clear_key(cls):
        cls.box = None


class MissingEncryptionKey(RuntimeError):
    def __init__(self, type_: type[Storable] | Storable, *args):
        type_ = type_.__class__ if isinstance(type_, Storable) else type_
        if len(args) == 0:
            args = (f'Missing encryption key for {type_}',)
        super().__init__(*args)
        self.storable: Storable = type_


async def does_table_exist(table_name) -> bool:
    # ToDo: LBYL instead of EAFP
    async with sql.connect(DB_FILE) as db:
        try:
            await db.execute(f'SELECT * FROM {table_name}')
            return True
        except sql.OperationalError as e:
            logger.debug(e)
            return False


async def make_table(blueprint: Storable):
    command = f'CREATE TABLE {blueprint.table_name} ('
    for var, var_type in blueprint.__annotations__.items():
        command += f'{var} {SQL_CAST[var_type]}, '
    command += f'PRIMARY KEY ({blueprint.primary_key_name}) );'
    await _write_db(command)


async def make_table_if_not_exist(blueprint: Storable):
    if not await does_table_exist(blueprint.table_name):
        await make_table(blueprint)


async def _write_db(command: str):
    logger.debug(command)
    async with sql.connect(DB_FILE) as db:
        await db.execute(command)
        await db.commit()


async def delete(data_type: type[S], **where):
    if not await does_table_exist(data_type.table_name):
        return

    command = f'DELETE FROM {data_type.table_name} ' \
              f'{_generate_where(**where)}'
    await _write_db(command)


async def _update_row(data: Storable):
    await make_table_if_not_exist(data)

    command = f'UPDATE {data.table_name} SET '
    # for attribute in data.__annotations__:
    #     if isinstance(val := getattr(data, attribute), str):
    #         command += f'{attribute} = "{val}", '
    #     else:
    #         command += f'{attribute} = {val}, '

    for attribute in data.__annotations__:
        val = getattr(data, attribute)
        command += f'{attribute} = '
        command += f'"{val}", ' if isinstance(val, str) else f'{val}, '

    command = f'{command[:-2]} WHERE {data.primary_key_name} = ' \
              f'{getattr(data, data.primary_key_name)}'
    await _write_db(command)


async def _insert_row(data: Storable):
    await make_table_if_not_exist(data)

    header = f'INSERT INTO {data.table_name} ('
    values = 'VALUES ('
    for attribute in data.__annotations__:
        header += f'{attribute}, '
        if isinstance(val := getattr(data, attribute), str):
            values += f'"{val}", '
        else:
            values += f'{val}, '
    command = f'{header[:-2]}) {values[:-2]});'

    await _write_db(command)


async def save_data(data: Storable):
    # ToDo: update table if exists but different schema
    await make_table_if_not_exist(data)
    where = f'{data.primary_key_name} = {getattr(data, data.primary_key_name)}'
    if len(await load_data_all(data.__class__, where=where)) == 0:
        await _insert_row(data)
    else:
        await _update_row(data)


async def save_datas(datas: Iterable[Storable]):
    tasks = []  # Python 3.11 ToDo: asyncio.TaskGroup()
    for data in datas:
        tasks.append(asyncio.create_task(save_data(data)))
    for task in tasks:
        await task


def _generate_where(**where) -> str:
    if len(where) == 0:
        return ''
    elif len(where) == 1 and (key := next(iter(where))).upper() == 'WHERE':
        return where[key] if 'where' in where[key].lower() \
            else f'WHERE {where[key]}'

    command = 'WHERE '
    for attr, val in where.items():
        command += f'{attr}={val} AND '
    return command[:-5]


async def load_data_all(data_type: type[S], decrypt: bool = True, **where) \
        -> list[S]:
    if not await does_table_exist(data_type.table_name):
        return []

    command = f'SELECT * FROM {data_type.table_name} ' \
              f'{_generate_where(**where)}'
    logger.debug(command)
    async with sql.connect(DB_FILE) as db:
        results = await db.execute_fetchall(command)
    if decrypt:
        return [data_type(*row).decrypt() for row in results]
    return [data_type(*row) for row in results]


async def load_data_gen(data_type: type[S], decrypt: bool = True, **where) \
        -> AsyncGenerator[S, None]:
    if not await does_table_exist(data_type.table_name):
        return

    command = f'SELECT * FROM {data_type.table_name} ' \
              f'{_generate_where(**where)}'
    logger.debug(command)
    async with sql.connect(DB_FILE) as db:
        async with db.execute(command) as cursor:
            async for row in cursor:
                if decrypt:
                    yield data_type(*row).decrypt()
                else:
                    yield data_type(*row)
