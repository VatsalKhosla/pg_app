"""Settings, read from the environment and from ``.env`` in the working directory (12-factor).

Three layers, so each process asks only for what it uses: ``LoggingSettings`` (the worker, for
now), ``DatabaseSettings`` (migrations) and ``Settings`` (the API). Business policy such as fees,
tokens and caps is data in the database, never configuration (ARCHITECTURE §22).
"""

from functools import lru_cache
from typing import Annotated, Final, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# The brand is undecided; it lives only here and in apps/web/src/config/brand.ts (CLAUDE.md).
BRAND_NAME: Final = "YourBrand"

Environment = Literal["local", "test", "staging", "production"]
DEPLOYED_ENVIRONMENTS: Final = frozenset({"staging", "production"})


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
    redis_url: SecretStr
    cors_allowed_origins: Annotated[tuple[str, ...], NoDecode] = ()
    max_request_body_bytes: int = Field(default=1_048_576, gt=0)
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "pg-platform-api"

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

    @field_validator("sentry_dsn", "otel_exporter_otlp_endpoint", mode="before")
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def _https_origins_when_deployed(self) -> Self:
        if self.app_env in DEPLOYED_ENVIRONMENTS:
            insecure = [o for o in self.cors_allowed_origins if not o.startswith("https://")]
            if insecure:
                msg = f"CORS origins must use https in {self.app_env}: {', '.join(insecure)}"
                raise ValueError(msg)
        return self

    @property
    def is_deployed(self) -> bool:
        return self.app_env in DEPLOYED_ENVIRONMENTS


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
