import asyncio
import sys

import aiosqlite as sql
import datetime as dt
import json
import logging
from logging.handlers import RotatingFileHandler
import time
from typing import AsyncIterable, Generic, Iterable, TypeVar


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

DATA = TypeVar("DATA", bound='Storable')


class Storable(Generic[DATA]):

    table_name = 'Storable'
    primary_key_name = 'table_name'

    def __init_subclass__(cls: type[DATA], **kwargs):
        if cls.table_name == super(cls, cls).table_name:
            cls.table_name = cls.__name__

        if cls.primary_key_name not in cls.__annotations__:
            raise AttributeError(f'{cls.__class__} has no annotation '
                                 f'{cls.primary_key_name}. Available: '
                                 f'{list[cls.__annotations__]}')
        super().__init_subclass__()

    async def save(self):
        await save_data(self)

    @classmethod
    async def load(cls, primary_key) -> DATA | None:
        where = f'{cls.primary_key_name} = {primary_key}'
        if len(results := await load_data_all(cls, where=where)) > 1:
            raise RuntimeError(f'More than one result ({len(results)})')
        if len(results) == 1:
            return results[0]
        return None

    @classmethod
    async def load_all(cls, **where) -> list[DATA]:
        return await load_data_all(cls, **where)

    @classmethod
    def load_iter(cls, **where) -> AsyncIterable[DATA]:
        return load_data_iter(cls, **where)


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


async def load_data_all(data_type: type[DATA], **where) \
        -> list[DATA]:
    if not await does_table_exist(data_type.table_name):
        return []

    command = f'SELECT * FROM {data_type.table_name} ' \
              f'{_generate_where(**where)}'
    logger.debug(command)
    async with sql.connect(DB_FILE) as db:
        results = await db.execute_fetchall(command)
    return [data_type(*row) for row in results]


async def load_data_iter(data_type: type[DATA], **where) \
        -> AsyncIterable[DATA]:
    if not await does_table_exist(data_type.table_name):
        return

    command = f'SELECT * FROM {data_type.table_name} ' \
              f'{_generate_where(**where)}'
    logger.debug(command)
    async with sql.connect(DB_FILE) as db:
        async with db.execute(command) as cursor:
            async for row in cursor:
                yield data_type(*row)
