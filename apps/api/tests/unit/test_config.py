from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from app.config import BRAND_NAME, TURNSTILE_TEST_SECRETS, Settings

if TYPE_CHECKING:
    from pathlib import Path

DATABASE_URL = "postgresql+asyncpg://app:db-secret-password@db.internal:5432/app"
REDIS_URL = "redis://:redis-secret-password@cache.internal:6379/0"


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    """A clean environment in a directory with no .env file."""
    monkeypatch.chdir(tmp_path)
    for name in (
        "APP_ENV",
        "DATABASE_URL",
        "REDIS_URL",
        "SECRET_KEY",
        "CORS_ALLOWED_ORIGINS",
        "SENTRY_DSN",
        "OTP_SENDER",
        "TURNSTILE_SECRET_KEY",
        "SESSION_COOKIE_DOMAIN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("SECRET_KEY", "test-only-secret-key-0123456789abcdef")
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


def test_the_secret_key_must_be_at_least_32_characters(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("SECRET_KEY", "too-short")

    with pytest.raises(ValidationError, match="secret_key"):
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


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_need_a_turnstile_secret(
    environment: pytest.MonkeyPatch, app_env: str
) -> None:
    environment.setenv("APP_ENV", app_env)
    environment.setenv("OTP_SENDER", "unavailable")

    with pytest.raises(ValidationError, match="TURNSTILE_SECRET_KEY is required"):
        Settings()


@pytest.mark.parametrize("secret", sorted(TURNSTILE_TEST_SECRETS))
def test_production_refuses_cloudflares_turnstile_test_secrets(
    environment: pytest.MonkeyPatch, secret: str
) -> None:
    environment.setenv("APP_ENV", "production")
    environment.setenv("TURNSTILE_SECRET_KEY", secret)
    environment.setenv("CORS_ALLOWED_ORIGINS", "https://www.example.in")
    environment.setenv("OTP_SENDER", "unavailable")

    with pytest.raises(ValidationError, match="Cloudflare test secret"):
        Settings()


def test_staging_may_use_the_always_pass_test_secret_for_smoke_tests(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("APP_ENV", "staging")
    environment.setenv("TURNSTILE_SECRET_KEY", "1x0000000000000000000000000000000AA")
    environment.setenv("CORS_ALLOWED_ORIGINS", "https://staging.example.in")
    environment.setenv("OTP_SENDER", "unavailable")

    assert Settings().turnstile_secret_key is not None


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_need_the_web_apps_origins(
    environment: pytest.MonkeyPatch, app_env: str
) -> None:
    environment.setenv("APP_ENV", app_env)
    environment.setenv("TURNSTILE_SECRET_KEY", "a-turnstile-secret")
    environment.setenv("OTP_SENDER", "unavailable")

    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings()


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_never_log_sign_in_codes(
    environment: pytest.MonkeyPatch, app_env: str
) -> None:
    environment.setenv("APP_ENV", app_env)
    environment.setenv("TURNSTILE_SECRET_KEY", "a-turnstile-secret")
    environment.setenv("CORS_ALLOWED_ORIGINS", "https://www.example.in")
    environment.setenv("OTP_SENDER", "console")

    with pytest.raises(ValidationError, match="OTP_SENDER=console"):
        Settings()


def test_a_deployed_environment_without_sms_runs_with_phone_sign_in_off(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("APP_ENV", "production")
    environment.setenv("TURNSTILE_SECRET_KEY", "a-turnstile-secret")
    environment.setenv("CORS_ALLOWED_ORIGINS", "https://www.example.in")
    environment.setenv("OTP_SENDER", "unavailable")

    settings = Settings()

    assert settings.otp_sender == "unavailable"
    assert settings.turnstile_secret_key is not None


def test_turnstile_is_solved_on_the_web_apps_hostnames(environment: pytest.MonkeyPatch) -> None:
    environment.setenv(
        "CORS_ALLOWED_ORIGINS", "https://www.example.in, https://Staging.Example.in:8443"
    )

    assert Settings().web_hostnames == {"www.example.in", "staging.example.in"}


@pytest.mark.parametrize("domain", ["https://example.com", "example", ".example.com/path"])
def test_the_session_cookie_domain_must_be_a_bare_domain(
    environment: pytest.MonkeyPatch, domain: str
) -> None:
    environment.setenv("SESSION_COOKIE_DOMAIN", domain)

    with pytest.raises(ValidationError, match="session_cookie_domain"):
        Settings()
