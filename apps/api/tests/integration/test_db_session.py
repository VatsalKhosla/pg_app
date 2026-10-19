import asyncio
from collections.abc import Callable, Iterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.core.db import DbSession
from app.main import create_app

pytestmark = pytest.mark.integration

type Requester = Callable[..., httpx.Response]
type SettingsFactory = Callable[..., Settings]


async def _execute(url: str, statement: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def _scalar(url: str, statement: str) -> object:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return (await connection.execute(text(statement))).scalar_one()
    finally:
        await engine.dispose()


def test_request_sessions_run_in_utc_with_the_configured_statement_timeout(
    make_settings: SettingsFactory, request_app: Requester, postgres_url: str
) -> None:
    app = create_app(make_settings(database_url=postgres_url, db_statement_timeout_ms=1234))

    @app.get("/test/session-settings")
    async def session_settings(session: DbSession) -> dict[str, str]:
        result = await session.execute(
            text(
                "SELECT current_setting('TimeZone'), current_setting('statement_timeout'),"
                " current_setting('application_name')"
            )
        )
        timezone, timeout, application = result.one()
        return {"timezone": timezone, "timeout": timeout, "application": application}

    response = request_app(app, "GET", "/test/session-settings")

    assert response.json() == {
        "timezone": "UTC",
        "timeout": "1234ms",
        "application": "pg-platform-api",
    }


@pytest.fixture
def probe_table(postgres_url: str) -> Iterator[str]:
    asyncio.run(_execute(postgres_url, "CREATE TABLE rollback_probe (id integer)"))
    try:
        yield "rollback_probe"
    finally:
        asyncio.run(_execute(postgres_url, "DROP TABLE rollback_probe"))


def test_work_a_request_leaves_uncommitted_is_rolled_back(
    make_settings: SettingsFactory,
    request_app: Requester,
    postgres_url: str,
    probe_table: str,
    csrf_headers: dict[str, str],
) -> None:
    # Services commit explicitly; anything they don't commit must never reach the database.
    app = create_app(make_settings(database_url=postgres_url))

    @app.post("/test/insert-without-commit")
    async def insert_without_commit(session: DbSession) -> dict[str, bool]:
        await session.execute(text(f"INSERT INTO {probe_table} (id) VALUES (1)"))  # noqa: S608
        return {"inserted": True}

    response = request_app(app, "POST", "/test/insert-without-commit", headers=csrf_headers)

    assert response.json() == {"inserted": True}
    assert asyncio.run(_scalar(postgres_url, f"SELECT count(*) FROM {probe_table}")) == 0  # noqa: S608
