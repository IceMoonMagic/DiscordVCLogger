import datetime as dt
import json
import logging
import os
import sys
import tempfile
import time
from logging.handlers import RotatingFileHandler
from typing import TypeVar

import aiosqlite as sql
import nacl.secret
from sqlalchemy import (
    BinaryExpression,
    DateTime,
    TypeDecorator,
    delete,
    inspect,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase


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


JSON_PATH = r"saves/bot_key.json"

LOG_NAME = "discord_bot"
logger = get_logger(__name__)

DB_FILE = r"saves/database.db"
TEMP_FILE = None

S = TypeVar("S", bound="Storable")


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


ENGINE = create_async_engine("sqlite://")


class Storable(DeclarativeBase):
    temp: bool = False

    encrypt_attrs: list = []
    box: nacl.secret.SecretBox | None = None

    async def save(self: S):
        # if not self.is_ready():
        #     raise MissingEncryptionKey(self.__class__)
        #
        # encrypted = {}
        # unique_chars: int = len(str(len(self.encrypt_attrs)))
        # primary_value = f"{getattr(self, self.primary_key_name)}"
        # nonce_base = (
        #     f"{primary_value[:24 - unique_chars]:0{24 - unique_chars}}"
        # )
        # for i, attr in enumerate(self.encrypt_attrs):
        #     nonce = f"{i:0{unique_chars}}{nonce_base}".encode()
        #
        #     raw_value: str = getattr(self, attr)
        #     bytes_value = raw_value.encode()
        #     encrypted_value = self.box.encrypt(bytes_value, nonce).ciphertext
        #     encrypted[attr] = encrypted_value.hex()

        async with AsyncSession(ENGINE) as session:
            session.add(self)
            await session.commit()

    def decrypt(self: S, decrypt_inplace: bool = True) -> S:
        work_on: S = self if decrypt_inplace else self.copy()

        if not work_on.is_ready():
            raise MissingEncryptionKey(self.__class__)

        unique_chars: int = len(str(len(work_on.encrypt_attrs)))
        primary_value = f"{getattr(work_on, work_on.primary_key_name)}"
        nonce_base = (
            f"{primary_value[:24 - unique_chars]:0{24 - unique_chars}}"
        )
        for i, attr in enumerate(work_on.encrypt_attrs):
            nonce = f"{i:0{unique_chars}}{nonce_base}".encode()

            hex_value: str = getattr(work_on, attr)
            bytes_value = bytes.fromhex(hex_value)
            decrypted_value = work_on.box.decrypt(bytes_value, nonce)
            # decrypted[attr]: str = decrypted_value.decode()
            setattr(work_on, attr, decrypted_value.decode())

        return work_on

    @classmethod
    async def load(
        cls: type[S], primary_key, decrypt: bool = True
    ) -> S | None:
        async with AsyncSession(ENGINE) as session:
            return await session.get(cls, primary_key)

    @classmethod
    async def load_all(
        cls: type[S], decrypt: bool = True, *where: BinaryExpression
    ) -> list[S]:
        async with AsyncSession(ENGINE) as session:
            stmt = select(cls)
            for w in where:
                stmt = stmt.where(w)
            return (await session.scalars(stmt)).all()

    @classmethod
    async def delete(cls, primary_key):
        pk = inspect(cls).primary_key
        async with AsyncSession(ENGINE) as session:
            stmt = delete(cls).where(pk == primary_key)
            await session.execute(stmt)

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
            args = (f"Missing encryption key for {type_}",)
        super().__init__(*args)
        self.storable: Storable = type_


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
