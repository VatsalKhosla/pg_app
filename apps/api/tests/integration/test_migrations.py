import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

API_ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = {"postgis", "btree_gist", "pg_trgm", "citext"}


async def _execute_autocommit(url: str, statement: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def _installed_extensions(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(text("SELECT extname FROM pg_extension"))
            return {row[0] for row in rows}
    finally:
        await engine.dispose()


@pytest.fixture
def empty_database_url(postgres_url: str) -> Iterator[str]:
    """A brand-new database, dropped afterwards, so each test migrates from nothing."""
    name = f"migrations_{uuid.uuid4().hex[:12]}"
    asyncio.run(_execute_autocommit(postgres_url, f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    finally:
        asyncio.run(_execute_autocommit(postgres_url, f'DROP DATABASE "{name}" WITH (FORCE)'))


def _alembic_config(url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def test_migrations_upgrade_downgrade_and_upgrade_again(empty_database_url: str) -> None:
    config = _alembic_config(empty_database_url)

    command.upgrade(config, "head")
    assert asyncio.run(_installed_extensions(empty_database_url)) >= EXTENSIONS

    command.downgrade(config, "base")
    assert asyncio.run(_installed_extensions(empty_database_url)).isdisjoint(EXTENSIONS)

    command.upgrade(config, "head")
    assert asyncio.run(_installed_extensions(empty_database_url)) >= EXTENSIONS
