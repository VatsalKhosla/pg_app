"""Real PostgreSQL and Valkey in throwaway containers (testcontainers), one of each per run.

PostgreSQL uses the image `make dev` runs, built from infra/postgres; the Valkey image is read
from infra/docker-compose.yml. Tests and local development therefore never drift apart.
"""

import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_FILE = REPO_ROOT / "infra" / "docker-compose.yml"
VALKEY_PASSWORD = "test"


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
