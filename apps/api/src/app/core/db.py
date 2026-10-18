"""Async SQLAlchemy: the engine, request-scoped sessions and the declarative base (ARCHITECTURE §5).

One ``AsyncSession`` per request or job. Services commit or roll back; repositories never commit;
whatever a request leaves uncommitted is rolled back when its session closes.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request
from sqlalchemy import BigInteger, DateTime, Identity, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.config import DatabaseSettings

# Explicit, stable names for every constraint and index, so migrations can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class AppendOnlyModel(Base):
    """Base for tables whose rows are written once (the audit log): an identity key and a
    creation time. Business times come from the injectable clock; these come from the database."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Model(AppendOnlyModel):
    """Base for every other table: identity key, ``created_at`` and ``updated_at`` (§6)."""

    __abstract__ = True

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def create_engine(settings: DatabaseSettings, *, application_name: str) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "server_settings": {
                "application_name": application_name,
                "timezone": "UTC",
                "statement_timeout": str(settings.db_statement_timeout_ms),
            }
        },
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]
