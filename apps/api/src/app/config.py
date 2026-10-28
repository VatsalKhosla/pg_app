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
BRAND_NAME: Final = "Fix Your Stay"

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
_DOMAIN: Final = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)+")
_EMAIL: Final = re.compile(r"[^@\s,]+@[a-z0-9-]+(\.[a-z0-9-]+)+")
# S3's rules for bucket names: 3 to 63 lowercase letters, digits, dots and hyphens.
_BUCKET: Final = r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"


class LoggingSettings(BaseSettings):
    # A rejected value stays out of the error, which ends up in logs: it may be a password in a
    # URL, a secret or someone's address.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
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
    # The web app's public address, where staff land after signing in with Google, and the API's
    # own, which Google's redirect URI starts with.
    site_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    # Staff sign-in with Google: the OAuth client of the founders' Google Cloud project. Unset, it
    # answers 503, and staff sign in with a phone code and an authenticator app instead.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    # The Google accounts allowed to sign in to staff tools, comma-separated: Google Workspace
    # domains (matched against the ID token's hd claim) and single addresses. Allowed isn't enough:
    # the account must also have been made staff (python -m app.manage staff add).
    staff_google_domains: Annotated[frozenset[str], NoDecode] = frozenset()
    staff_google_emails: Annotated[frozenset[str], NoDecode] = frozenset()
    # The version of the privacy notice the web app shows, which every consent records (DPDP).
    # Changing it asks everyone to agree again. A "draft" one (not yet reviewed by a lawyer)
    # can't go to production.
    privacy_notice_version: str = Field(default="draft-1", pattern=r"^[a-z0-9][a-z0-9.-]{0,63}$")
    # The owner agreement owners accept (ADR 0025): a file in catalog/data/agreements. Changing it
    # asks every owner to accept again. A "draft" one (not yet reviewed by a lawyer) can't go to
    # production.
    owner_agreement_version: str = Field(default="draft-2", pattern=r"^[a-z0-9][a-z0-9.-]{0,63}$")

    # Object storage (S3; SeaweedFS locally). Uploads and private files go to one bucket; listing
    # media anyone may see go to the other, which the CDN serves when deployed. On AWS the endpoint
    # and keys stay unset: the task's IAM role signs requests.
    s3_endpoint_url: str | None = None
    s3_region: str = "ap-south-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    media_private_bucket: str = Field(default="pg-platform-private", pattern=_BUCKET)
    media_public_bucket: str = Field(default="pg-platform-media", pattern=_BUCKET)
    # Where public media are read from: the CDN when deployed, the public bucket itself locally.
    media_public_base_url: str = "http://127.0.0.1:8333/pg-platform-media"

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

    @field_validator("staff_google_domains", "staff_google_emails", mode="before")
    @classmethod
    def _split_lowercase(cls, value: object) -> object:
        # STAFF_GOOGLE_DOMAINS=example.com,example.in
        if isinstance(value, str):
            return frozenset(item.strip().lower() for item in value.split(",") if item.strip())
        return value

    @field_validator(
        "sentry_dsn",
        "otel_exporter_otlp_endpoint",
        "session_cookie_domain",
        "turnstile_secret_key",
        "google_client_id",
        "google_client_secret",
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

    @field_validator("site_url", "api_url")
    @classmethod
    def _base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
        ):
            msg = "must be an http(s) address without a path, such as https://www.example.com"
            raise ValueError(msg)
        return value.rstrip("/")

    @field_validator("media_public_base_url")
    @classmethod
    def _media_base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.query:
            msg = "must be an http(s) address, such as https://media.example.com"
            raise ValueError(msg)
        return value.rstrip("/")

    @model_validator(mode="after")
    def _storage_keys_together(self) -> Self:
        if (self.s3_access_key_id is None) != (self.s3_secret_access_key is None):
            msg = "set S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY together, or neither"
            raise ValueError(msg)
        if self.media_private_bucket == self.media_public_bucket:
            msg = "MEDIA_PRIVATE_BUCKET and MEDIA_PUBLIC_BUCKET must differ"
            raise ValueError(msg)
        return self

    @field_validator("staff_google_domains")
    @classmethod
    def _bare_domains(cls, value: frozenset[str]) -> frozenset[str]:
        invalid = sorted(domain for domain in value if not _DOMAIN.fullmatch(domain))
        if invalid:
            msg = f"must be domains such as example.com: {', '.join(invalid)}"
            raise ValueError(msg)
        return value

    @field_validator("staff_google_emails")
    @classmethod
    def _addresses(cls, value: frozenset[str]) -> frozenset[str]:
        # The addresses themselves stay out of the message: it ends up in logs.
        invalid = sum(1 for address in value if not _EMAIL.fullmatch(address))
        if invalid:
            msg = f"{invalid} of the addresses aren't email addresses"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _https_when_deployed(self) -> Self:
        if self.app_env in DEPLOYED_ENVIRONMENTS:
            addresses = (
                *self.cors_allowed_origins,
                self.site_url,
                self.api_url,
                self.media_public_base_url,
            )
            insecure = [address for address in addresses if not address.startswith("https://")]
            if insecure:
                msg = (
                    "CORS origins, SITE_URL, API_URL and MEDIA_PUBLIC_BASE_URL must use https in "
                    f"{self.app_env}: {', '.join(insecure)}"
                )
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _google_sign_in_complete(self) -> Self:
        if (self.google_client_id is None) != (self.google_client_secret is None):
            msg = "set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET together, or neither"
            raise ValueError(msg)
        if self.google_client_id is not None and not (
            self.staff_google_domains or self.staff_google_emails
        ):
            msg = "Google sign-in needs STAFF_GOOGLE_DOMAINS or STAFF_GOOGLE_EMAILS"
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

    @model_validator(mode="after")
    def _reviewed_privacy_notice_in_production(self) -> Self:
        if self.app_env == "production" and self.privacy_notice_version.startswith("draft"):
            msg = (
                "PRIVACY_NOTICE_VERSION is a draft; production needs the reviewed notice's version"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _reviewed_owner_agreement_in_production(self) -> Self:
        if self.app_env == "production" and self.owner_agreement_version.startswith("draft"):
            msg = (
                "OWNER_AGREEMENT_VERSION is a draft; production needs the reviewed agreement's"
                " version"
            )
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

    @property
    def google_hosted_domain_hint(self) -> str | None:
        """The one Workspace domain Google's account chooser may be narrowed to, when staff can
        only come from one domain (a convenience; the hd claim is what's checked)."""
        if len(self.staff_google_domains) == 1 and not self.staff_google_emails:
            return next(iter(self.staff_google_domains))
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
