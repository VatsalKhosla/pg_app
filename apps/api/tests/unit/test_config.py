from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from app.config import BRAND_NAME, Settings

if TYPE_CHECKING:
    from pathlib import Path

DATABASE_URL = "postgresql+asyncpg://app:db-secret-password@db.internal:5432/app"
REDIS_URL = "redis://:redis-secret-password@cache.internal:6379/0"


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    """A clean environment in a directory with no .env file."""
    monkeypatch.chdir(tmp_path)
    for name in ("APP_ENV", "DATABASE_URL", "REDIS_URL", "CORS_ALLOWED_ORIGINS", "SENTRY_DSN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    return monkeypatch


def test_reads_the_environment_and_keeps_secrets_out_of_repr(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, http://127.0.0.1:3000")

    settings = Settings()

    assert settings.database_url.get_secret_value() == DATABASE_URL
    assert settings.cors_allowed_origins == ("http://localhost:3000", "http://127.0.0.1:3000")
    assert "db-secret-password" not in repr(settings)
    assert "redis-secret-password" not in repr(settings)


def test_reads_dot_env_in_the_working_directory(
    environment: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment.delenv("REDIS_URL")
    (tmp_path / ".env").write_text(f"REDIS_URL={REDIS_URL}\nLOG_LEVEL=DEBUG\n")

    settings = Settings()

    assert settings.redis_url.get_secret_value() == REDIS_URL
    assert settings.log_level == "DEBUG"


def test_empty_optional_values_mean_unset(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("SENTRY_DSN", "")
    environment.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    settings = Settings()

    assert settings.sentry_dsn is None
    assert settings.otel_exporter_otlp_endpoint is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATABASE_URL", "postgresql://app:pw@db/app"),  # sync driver
        ("REDIS_URL", "http://cache.internal:6379"),
    ],
)
def test_rejects_urls_with_the_wrong_scheme(
    environment: pytest.MonkeyPatch, name: str, value: str
) -> None:
    environment.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_require_https_origins(
    environment: pytest.MonkeyPatch, app_env: str
) -> None:
    environment.setenv("APP_ENV", app_env)
    environment.setenv("CORS_ALLOWED_ORIGINS", "https://www.example.in,http://staging.example.in")

    with pytest.raises(ValidationError, match="must use https"):
        Settings()


def test_test_settings_ignore_the_environment_and_dot_env(
    environment: pytest.MonkeyPatch, tmp_path: Path, make_settings: Callable[..., Settings]
) -> None:
    # A developer's real configuration must never leak into the test suite.
    (tmp_path / ".env").write_text("LOG_LEVEL=DEBUG\nSENTRY_DSN=https://key@sentry.invalid/1\n")
    environment.setenv("DB_POOL_SIZE", "99")

    settings = make_settings()

    assert settings.log_level == "INFO"
    assert settings.sentry_dsn is None
    assert settings.db_pool_size == 10


def test_the_brand_name_is_still_a_placeholder() -> None:
    # Undecided (CLAUDE.md); change it here and in apps/web/src/config/brand.ts together.
    assert BRAND_NAME == "YourBrand"
