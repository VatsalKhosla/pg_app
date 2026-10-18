"""Alembic environment: applies migrations to DATABASE_URL over asyncpg, one transaction each.

Tests pass the URL through the Alembic config (``sqlalchemy.url``); everywhere else it comes
from the environment. Migrations run as their own step before a new API version starts
(ARCHITECTURE §21) and get no statement timeout, since index builds can be slow.
"""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import DatabaseSettings
from app.core.logging import configure_logging
from app.models import Base

config = context.config
target_metadata = Base.metadata

# Tables that extensions create and own (PostGIS's spatial reference systems). Autogenerate must
# never propose dropping them just because no model describes them.
EXTENSION_TABLES = frozenset({"spatial_ref_sys"})


def _include_name(name: str | None, type_: str, _parent_names: object) -> bool:
    return not (type_ == "table" and name in EXTENSION_TABLES)


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    settings = DatabaseSettings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    return settings.database_url.get_secret_value()


def _configure(*, connection: Connection | None = None, url: str | None = None) -> None:
    offline = connection is None
    context.configure(
        connection=connection,
        url=url,
        literal_binds=offline,
        dialect_opts={"paramstyle": "named"} if offline else None,
        target_metadata=target_metadata,
        include_name=_include_name,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
    )


def run_migrations_offline() -> None:
    _configure(url=_database_url())
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(
        _database_url(),
        poolclass=pool.NullPool,
        connect_args={"server_settings": {"application_name": "pg-platform-migrations"}},
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
