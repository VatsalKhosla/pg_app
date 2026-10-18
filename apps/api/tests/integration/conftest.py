"""Real PostgreSQL and Valkey in throwaway containers (testcontainers), one of each per run.

PostgreSQL uses the image `make dev` runs, built from infra/postgres; the Valkey image is read
from infra/docker-compose.yml. Tests and local development therefore never drift apart.
"""

import asyncio
import re
import shutil
import subprocess
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

REPO_ROOT = Path(__file__).resolve().parents[4]
API_ROOT = REPO_ROOT / "apps" / "api"
COMPOSE_FILE = REPO_ROOT / "infra" / "docker-compose.yml"
VALKEY_PASSWORD = "test"

type Sessionmaker = async_sessionmaker[AsyncSession]
type RunDb = Callable[[Callable[[Sessionmaker], Awaitable[Any]]], Any]


def alembic_config(url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


async def execute_autocommit(url: str, statement: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


def compose_image(service: str) -> str:
    match = re.search(
        rf"^  {service}:\n(?:    .*\n)*?    image: (\S+)$", COMPOSE_FILE.read_text(), re.MULTILINE
    )
    if match is None:
        msg = f"no image for service {service!r} in {COMPOSE_FILE}"
        raise LookupError(msg)
    return match.group(1)


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    docker = shutil.which("docker")
    assert docker is not None, "integration tests need Docker"
    # Cheap when nothing changed: Docker reuses its build cache.
    subprocess.run(
        [docker, "compose", "-f", str(COMPOSE_FILE), "build", "--quiet", "postgres"], check=True
    )
    with PostgresContainer(
        compose_image("postgres"), username="test", password="test", dbname="test", driver="asyncpg"
    ) as container:
        yield container


@pytest.fixture(scope="session")
def postgres_url(postgres: PostgresContainer) -> str:
    return postgres.get_connection_url()


@pytest.fixture(scope="session")
def database_url(postgres_url: str) -> str:
    """A database migrated to head once per run, for tests that need the schema."""
    asyncio.run(execute_autocommit(postgres_url, 'CREATE DATABASE "app_test"'))
    url = make_url(postgres_url).set(database="app_test").render_as_string(hide_password=False)
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture
def run_db(database_url: str) -> RunDb:
    """Run an async scenario against the migrated database, on a fresh engine and event loop."""

    def run(scenario: Callable[[Sessionmaker], Awaitable[Any]]) -> Any:
        async def wrapped() -> Any:
            engine = create_async_engine(database_url, poolclass=NullPool)
            try:
                return await scenario(async_sessionmaker(engine, expire_on_commit=False))
            finally:
                await engine.dispose()

        return asyncio.run(wrapped())

    return run


@pytest.fixture(scope="session")
def valkey() -> Iterator[DockerContainer]:
    container = (
        DockerContainer(compose_image("valkey"))
        .with_command(
            ["valkey-server", "--requirepass", VALKEY_PASSWORD, "--save", "", "--appendonly", "no"]
        )
        .with_exposed_ports(6379)
        .waiting_for(LogMessageWaitStrategy("Ready to accept connections"))
    )
    with container:
        yield container


@pytest.fixture(scope="session")
def valkey_url(valkey: DockerContainer) -> str:
    host, port = valkey.get_container_host_ip(), valkey.get_exposed_port(6379)
    return f"redis://:{VALKEY_PASSWORD}@{host}:{port}/0"
