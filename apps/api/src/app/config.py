"""Settings, read from the environment and from ``.env`` in the working directory (12-factor).

Three layers, so each process asks only for what it uses: ``LoggingSettings`` (the worker, for
now), ``DatabaseSettings`` (migrations) and ``Settings`` (the API). Business policy such as fees,
tokens and caps is data in the database, never configuration (ARCHITECTURE §22).
"""

import re
from functools import lru_cache
from typing import Annotated, Final, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# The brand is undecided; it lives only here and in apps/web/src/config/brand.ts (CLAUDE.md).
BRAND_NAME: Final = "YourBrand"

Environment = Literal["local", "test", "staging", "production"]
DEPLOYED_ENVIRONMENTS: Final = frozenset({"staging", "production"})
# Cloudflare's published Turnstile test secrets (always pass, always fail, always "duplicate"):
# fine for staging smoke tests, never for production.
TURNSTILE_TEST_SECRETS: Final = frozenset(
    {
        "1x0000000000000000000000000000000AA",
        "2x0000000000000000000000000000000AA",
        "3x0000000000000000000000000000000AA",
    }
)


class LoggingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    app_env: Environment = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"


class DatabaseSettings(LoggingSettings):
    database_url: SecretStr
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout_seconds: float = Field(default=5.0, gt=0)
    db_statement_timeout_ms: int = Field(default=15_000, ge=0)

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            msg = "must be a postgresql+asyncpg:// URL"
            raise ValueError(msg)
        return value


class Settings(DatabaseSettings):
    # Keys the HMACs that protect sign-in codes, CSRF tokens and rate-limit keys.
    secret_key: SecretStr = Field(min_length=32)
    redis_url: SecretStr
    cors_allowed_origins: Annotated[tuple[str, ...], NoDecode] = ()
    # The parent domain session cookies apply to (".example.com") when the web app and the API
    # are on sibling subdomains. Unset: host-only cookies, as in local development.
    session_cookie_domain: str | None = None
    max_request_body_bytes: int = Field(default=1_048_576, gt=0)
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "pg-platform-api"
    # How sign-in codes reach phones. "console" writes them to the log, for local development and
    # tests only. "unavailable" turns phone sign-in off (503), for a deployed environment until the
    # founders choose the SMS provider (DLT-registered), whose adapter then joins this list.
    otp_sender: Literal["console", "unavailable"] = "console"
    # Cloudflare Turnstile's secret key. Unset, every human check passes (local and tests only).
    turnstile_secret_key: SecretStr | None = None

    # Worker: concurrent outbox consumers, jobs per claim, idle poll interval, job lease.
    worker_concurrency: int = Field(default=2, ge=1)
    worker_batch_size: int = Field(default=10, ge=1)
    worker_poll_interval_seconds: float = Field(default=1.0, gt=0)
    outbox_lease_seconds: int = Field(default=300, ge=10)

    @field_validator("redis_url")
    @classmethod
    def _require_redis_scheme(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            msg = "must be a redis:// or rediss:// URL"
            raise ValueError(msg)
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # CORS_ALLOWED_ORIGINS=https://a.example,https://b.example
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    @field_validator(
        "sentry_dsn",
        "otel_exporter_otlp_endpoint",
        "session_cookie_domain",
        "turnstile_secret_key",
        mode="before",
    )
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("session_cookie_domain")
    @classmethod
    def _bare_domain(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"\.?[a-z0-9-]+(\.[a-z0-9-]+)+", value):
            msg = "must be a domain such as .example.com, without scheme or path"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _https_origins_when_deployed(self) -> Self:
        if self.app_env in DEPLOYED_ENVIRONMENTS:
            insecure = [o for o in self.cors_allowed_origins if not o.startswith("https://")]
            if insecure:
                msg = f"CORS origins must use https in {self.app_env}: {', '.join(insecure)}"
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _real_sign_in_checks_when_deployed(self) -> Self:
        if self.app_env not in DEPLOYED_ENVIRONMENTS:
            return self
        if self.turnstile_secret_key is None:
            msg = f"TURNSTILE_SECRET_KEY is required in {self.app_env}"
            raise ValueError(msg)
        if (
            self.app_env == "production"
            and self.turnstile_secret_key.get_secret_value() in TURNSTILE_TEST_SECRETS
        ):
            msg = "TURNSTILE_SECRET_KEY is a Cloudflare test secret; not allowed in production"
            raise ValueError(msg)
        if not self.cors_allowed_origins:
            # The browser calls the API from these origins, and solves Turnstile on them.
            msg = f"CORS_ALLOWED_ORIGINS (the web app's origins) is required in {self.app_env}"
            raise ValueError(msg)
        if self.otp_sender == "console":
            msg = f"OTP_SENDER=console logs sign-in codes; not allowed in {self.app_env}"
            raise ValueError(msg)
        return self

    @property
    def is_deployed(self) -> bool:
        return self.app_env in DEPLOYED_ENVIRONMENTS

    @property
    def web_hostnames(self) -> frozenset[str]:
        """The web app's hostnames, from its CORS origins: where Turnstile may be solved."""
        return frozenset(
            host for origin in self.cors_allowed_origins if (host := urlsplit(origin).hostname)
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
