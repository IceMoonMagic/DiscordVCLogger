import datetime as dt
import json
import logging
import os
import sys
import tempfile
import time
from logging.handlers import RotatingFileHandler
from typing import Any, TypeVar

import aiosqlite as sql
import nacl.secret
from sqlalchemy import (
    BinaryExpression,
    DateTime,
    LargeBinary,
    StaticPool,
    TypeDecorator,
    delete,
    inspect,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    QueryableAttribute,
    defer,
)
from sqlalchemy import func


def setup_logging(
    to_stdout: bool = True,
    local_level: int = logging.INFO,
    root_level: int = logging.WARNING,
):
    logging.Formatter.converter = time.gmtime

    root_logger = logging.getLogger()
    local_logger = logging.getLogger(LOG_NAME)

    now = dt.datetime.now(tz=dt.timezone.utc)
    os.makedirs("logs", exist_ok=True)

    root_error_handler = RotatingFileHandler(
        f'logs/{now.strftime(LOG_NAME + "_notable_root")}.log',
        maxBytes=524288,
        backupCount=3,
    )
    local_error_handler = RotatingFileHandler(
        f'logs/{now.strftime(LOG_NAME + "_notable_local")}.log',
        maxBytes=524288,
        backupCount=3,
    )
    standard_log_handler = RotatingFileHandler(
        f'logs/{now.strftime(LOG_NAME + "_standard")}.log',
        maxBytes=524288,
        backupCount=3,
    )
    console_handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter(
        "{asctime}|{levelname}|{lineno}|{name}|{message}",
        "%Y-%m-%d %H:%M:%S",
        "{",
    )

    root_error_handler.setFormatter(formatter)
    local_error_handler.setFormatter(formatter)
    standard_log_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    root_error_handler.setLevel(logging.WARNING)
    local_error_handler.setLevel(logging.WARNING)

    root_logger.setLevel(root_level)
    local_logger.setLevel(local_level)

    root_logger.addHandler(root_error_handler)
    local_logger.addHandler(local_error_handler)
    local_logger.addHandler(standard_log_handler)
    if to_stdout:
        local_logger.addHandler(console_handler)


def get_logger(name) -> logging.Logger:
    return logging.getLogger(f"{LOG_NAME}.{name}")


def get_json_data(key: str = "") -> dict:
    with open(JSON_PATH) as file:
        data = json.load(file)
    for k in key.split("."):
        data = data.get(k, {})
    return data


def init_box(key: bytes | str):
    global BOX
    if isinstance(key, str):
        key = key.encode()
    if (length := len(key)) < 32:
        key += b" " * (32 - length)
    BOX = nacl.secret.SecretBox(key)


async def init_tables(drop_tables: bool = False):
    async with ENGINE.begin() as conn:
        if drop_tables:
            await conn.run_sync(Storable.metadata.drop_all)
        await conn.run_sync(Storable.metadata.create_all)


JSON_PATH = r"saves/bot_key.json"

LOG_NAME = "discord_bot"
logger = get_logger(__name__)

DB_FILE = r"saves/database.db"
TEMP_FILE = None

BOX: nacl.secret.SecretBox | None = None

S = TypeVar("S", bound="Storable")


class EncryptedStr(TypeDecorator):
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str, dialect) -> bytes:
        if BOX is None:
            raise MissingEncryptionKey
        return BOX.encrypt(value.encode())

    def process_result_value(self, value: bytes, dialect) -> str:
        if BOX is None:
            raise MissingEncryptionKey
        return BOX.decrypt(value).decode()


# https://docs.sqlalchemy.org/en/14/core/custom_types.html#store-timezone-aware-timestamps-as-timezone-naive-utc
class TZDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = value.astimezone(dt.UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = value.replace(tzinfo=dt.UTC)
        return value


ENGINE = create_async_engine(
    "sqlite+aiosqlite:///saves/database.db", poolclass=StaticPool
)


class Storable(DeclarativeBase):
    temp: bool = False

    async def save(self: S):
        async with AsyncSession(ENGINE) as session:
            session.add(self)
            await session.commit()

    @classmethod
    async def count(cls, *where: BinaryExpression) -> int:
        async with AsyncSession(ENGINE) as session:
            stmt = select(func.count()).select_from(cls)
            for w in where:
                stmt = stmt.where(w)
            return await session.scalar(stmt)

    @classmethod
    async def load(cls: type[S], primary_key) -> S | None:
        async with AsyncSession(ENGINE) as session:
            return await session.get(cls, primary_key)

    @classmethod
    async def load_all(
        cls: type[S],
        *where: BinaryExpression,
        defer_: list[QueryableAttribute] = None,
    ) -> list[S]:
        async with AsyncSession(ENGINE) as session:
            stmt = select(cls)
            for w in where:
                stmt = stmt.where(w)
            if defer_ is not None:
                stmt = stmt.options(defer(*defer_))
            return (await session.scalars(stmt)).all()

    @classmethod
    async def delete(cls: type[S], primary_key: Any | S):
        if isinstance(primary_key, cls):
            async with AsyncSession(ENGINE) as session:
                await session.delete(primary_key)
                await session.commit()
                return

        pk = inspect(cls).primary_key
        async with AsyncSession(ENGINE) as session:
            stmt = delete(cls).where(pk[0] == primary_key)
            await session.execute(stmt)
            await session.commit()

    @classmethod
    async def delete_all(cls, *where: BinaryExpression):
        async with AsyncSession(ENGINE) as session:
            stmt = delete(cls)
            for w in where:
                stmt = stmt.where(w)
            await session.execute(stmt)
            await session.commit()


class MissingEncryptionKey(RuntimeError):
    def __init__(self, *args):
        if len(args) == 0:
            args = (f"Missing encryption key",)
        super().__init__(*args)


async def does_table_exist(table_name, temp: bool) -> bool:
    async with sql.connect(get_db_file(temp)) as db:
        command = f'SELECT sql FROM sqlite_master WHERE name = "{table_name}"'
        logger.debug(command)
        table_sql = await db.execute_fetchall(command)
        return bool(table_sql)


def get_temp_file() -> str:
    global TEMP_FILE
    if TEMP_FILE:
        return TEMP_FILE
    fd, TEMP_FILE = tempfile.mkstemp(prefix=sys.argv[0][:-3], suffix=".db")
    return TEMP_FILE


def get_db_file(temp: bool) -> str:
    if temp:
        return get_temp_file()
    return DB_FILE


def delete_temp_file():
    # ToDo: Temp file if program is unnaturally canceled
    global TEMP_FILE
    if isinstance(TEMP_FILE, str):
        os.remove(TEMP_FILE)
        TEMP_FILE = None
