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
        "SITE_URL",
        "API_URL",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "STAFF_GOOGLE_DOMAINS",
        "STAFF_GOOGLE_EMAILS",
        "PRIVACY_NOTICE_VERSION",
        "REVALIDATE_SECRET",
        "TEXT_SENDER",
        "POSTHOG_PROJECT_KEY",
        "POSTHOG_HOST",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("SECRET_KEY", "test-only-secret-key-0123456789abcdef")
    return monkeypatch


def _deployed(environment: pytest.MonkeyPatch, app_env: str = "production") -> pytest.MonkeyPatch:
    """Everything a deployed environment requires; each test then takes one thing away."""
    for name, value in {
        "APP_ENV": app_env,
        "CORS_ALLOWED_ORIGINS": "https://www.example.in",
        "SITE_URL": "https://www.example.in",
        "API_URL": "https://api.example.in",
        "MEDIA_PUBLIC_BASE_URL": "https://media.example.in",
        "TURNSTILE_SECRET_KEY": "a-turnstile-secret",
        "OTP_SENDER": "unavailable",
        "PRIVACY_NOTICE_VERSION": "2027-01",
        "OWNER_AGREEMENT_VERSION": "2027-01",
        "REVALIDATE_SECRET": "a-revalidation-secret-of-32-chars!!",
        "TEXT_SENDER": "unavailable",
    }.items():
        environment.setenv(name, value)
    return environment


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


def test_the_brand_name_is_the_founders_choice() -> None:
    # Decided by the founders (CLAUDE.md); change it here and in apps/web/src/config/brand.ts
    # together, with a new owner agreement version (its text names the brand).
    assert BRAND_NAME == "Fix Your Stay"


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_need_a_turnstile_secret(
    environment: pytest.MonkeyPatch, app_env: str
) -> None:
    _deployed(environment, app_env).delenv("TURNSTILE_SECRET_KEY")

    with pytest.raises(ValidationError, match="TURNSTILE_SECRET_KEY is required"):
        Settings()


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_need_the_revalidation_secret(
    environment: pytest.MonkeyPatch, app_env: str
) -> None:
    _deployed(environment, app_env).delenv("REVALIDATE_SECRET")

    with pytest.raises(ValidationError, match=r"REVALIDATE_SECRET .* is required"):
        Settings()


def test_the_revalidation_secret_is_long_and_empty_means_unset(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("REVALIDATE_SECRET", "")
    assert Settings().revalidate_secret is None

    environment.setenv("REVALIDATE_SECRET", "too-short")
    with pytest.raises(ValidationError, match="at least 32"):
        Settings()


@pytest.mark.parametrize("secret", sorted(TURNSTILE_TEST_SECRETS))
def test_production_refuses_cloudflares_turnstile_test_secrets(
    environment: pytest.MonkeyPatch, secret: str
) -> None:
    _deployed(environment).setenv("TURNSTILE_SECRET_KEY", secret)

    with pytest.raises(ValidationError, match="Cloudflare test secret"):
        Settings()


def test_staging_may_use_the_always_pass_test_secret_for_smoke_tests(
    environment: pytest.MonkeyPatch,
) -> None:
    _deployed(environment, "staging").setenv(
        "TURNSTILE_SECRET_KEY", "1x0000000000000000000000000000000AA"
    )

    assert Settings().turnstile_secret_key is not None


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_need_the_web_apps_origins(
    environment: pytest.MonkeyPatch, app_env: str
) -> None:
    _deployed(environment, app_env).delenv("CORS_ALLOWED_ORIGINS")

    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings()


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_never_log_sign_in_codes(
    environment: pytest.MonkeyPatch, app_env: str
) -> None:
    _deployed(environment, app_env).setenv("OTP_SENDER", "console")

    with pytest.raises(ValidationError, match="OTP_SENDER=console"):
        Settings()


def test_a_deployed_environment_without_sms_runs_with_phone_sign_in_off(
    environment: pytest.MonkeyPatch,
) -> None:
    settings = (_deployed(environment), Settings())[1]

    assert settings.otp_sender == "unavailable"
    assert settings.turnstile_secret_key is not None


def test_turnstile_is_solved_on_the_web_apps_hostnames(environment: pytest.MonkeyPatch) -> None:
    environment.setenv(
        "CORS_ALLOWED_ORIGINS", "https://www.example.in, https://Staging.Example.in:8443"
    )

    assert Settings().web_hostnames == {"www.example.in", "staging.example.in"}


@pytest.mark.parametrize("name", ["SITE_URL", "API_URL"])
def test_deployed_environments_need_https_for_the_site_and_the_api(
    environment: pytest.MonkeyPatch, name: str
) -> None:
    _deployed(environment).setenv(name, "http://www.example.in")

    with pytest.raises(ValidationError, match="must use https"):
        Settings()


@pytest.mark.parametrize(
    "address",
    ["www.example.in", "https://www.example.in/app", "https://www.example.in?a=1", "ftp://a.in"],
    ids=["no-scheme", "path", "query", "ftp"],
)
def test_the_site_and_api_addresses_are_origins_without_a_path(
    environment: pytest.MonkeyPatch, address: str
) -> None:
    environment.setenv("SITE_URL", address)

    with pytest.raises(ValidationError, match="site_url"):
        Settings()


def test_a_trailing_slash_is_dropped_from_the_site_and_api_addresses(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("API_URL", "https://api.example.in/")

    assert Settings().api_url == "https://api.example.in"


def test_google_sign_in_needs_the_client_id_and_secret_together(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("GOOGLE_CLIENT_ID", "1234-test.apps.googleusercontent.com")
    environment.setenv("STAFF_GOOGLE_DOMAINS", "example.in")

    with pytest.raises(ValidationError, match="GOOGLE_CLIENT_SECRET together"):
        Settings()


def test_google_sign_in_needs_someone_allowed_to_use_it(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("GOOGLE_CLIENT_ID", "1234-test.apps.googleusercontent.com")
    environment.setenv("GOOGLE_CLIENT_SECRET", "client-secret")

    with pytest.raises(ValidationError, match="STAFF_GOOGLE_DOMAINS or STAFF_GOOGLE_EMAILS"):
        Settings()


def test_allowed_google_domains_and_addresses_are_read_in_lowercase(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("STAFF_GOOGLE_DOMAINS", "Example.in, example.com")
    environment.setenv("STAFF_GOOGLE_EMAILS", "Founder@Gmail.com")

    settings = Settings()

    assert settings.staff_google_domains == {"example.in", "example.com"}
    assert settings.staff_google_emails == {"founder@gmail.com"}
    # With single addresses allowed too, Google's account chooser stays open.
    assert settings.google_hosted_domain_hint is None


def test_a_single_allowed_domain_narrows_googles_account_chooser(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("STAFF_GOOGLE_DOMAINS", "example.in")

    assert Settings().google_hosted_domain_hint == "example.in"


@pytest.mark.parametrize("domain", ["https://example.in", "example"])
def test_allowed_domains_must_be_bare_domains(environment: pytest.MonkeyPatch, domain: str) -> None:
    environment.setenv("STAFF_GOOGLE_DOMAINS", domain)

    with pytest.raises(ValidationError, match="staff_google_domains"):
        Settings()


def test_allowed_addresses_must_be_addresses_and_stay_out_of_the_error(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("STAFF_GOOGLE_EMAILS", "founder.at.gmail.com")

    with pytest.raises(ValidationError, match="staff_google_emails") as error:
        Settings()
    # Someone's address must not reach the error, and so the logs.
    assert "founder" not in str(error.value)


def test_a_rejected_secret_never_appears_in_the_error(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("DATABASE_URL", "postgresql://app:db-secret-password@db.internal/app")

    with pytest.raises(ValidationError) as error:
        Settings()
    assert "db-secret-password" not in str(error.value)


@pytest.mark.parametrize("domain", ["https://example.com", "example", ".example.com/path"])
def test_the_session_cookie_domain_must_be_a_bare_domain(
    environment: pytest.MonkeyPatch, domain: str
) -> None:
    environment.setenv("SESSION_COOKIE_DOMAIN", domain)

    with pytest.raises(ValidationError, match="session_cookie_domain"):
        Settings()


def test_production_needs_a_reviewed_privacy_notice(environment: pytest.MonkeyPatch) -> None:
    _deployed(environment).setenv("PRIVACY_NOTICE_VERSION", "draft-2")

    with pytest.raises(ValidationError, match="PRIVACY_NOTICE_VERSION is a draft"):
        Settings()


def test_staging_may_run_with_a_draft_privacy_notice(environment: pytest.MonkeyPatch) -> None:
    _deployed(environment, "staging").setenv("PRIVACY_NOTICE_VERSION", "draft-2")

    assert Settings().privacy_notice_version == "draft-2"


def test_production_needs_a_reviewed_owner_agreement(environment: pytest.MonkeyPatch) -> None:
    _deployed(environment).setenv("OWNER_AGREEMENT_VERSION", "draft-2")

    with pytest.raises(ValidationError, match="OWNER_AGREEMENT_VERSION is a draft"):
        Settings()


def test_staging_may_run_with_a_draft_owner_agreement(environment: pytest.MonkeyPatch) -> None:
    _deployed(environment, "staging").setenv("OWNER_AGREEMENT_VERSION", "draft-2")

    assert Settings().owner_agreement_version == "draft-2"


@pytest.mark.parametrize("version", ["", "Draft 1", "../draft-1", "x" * 65])
def test_an_owner_agreement_version_is_a_short_lowercase_label(
    environment: pytest.MonkeyPatch, version: str
) -> None:
    environment.setenv("OWNER_AGREEMENT_VERSION", version)

    with pytest.raises(ValidationError, match="owner_agreement_version"):
        Settings()


@pytest.mark.parametrize("version", ["", "Draft 1", "v1/2", "x" * 65])
def test_a_privacy_notice_version_is_a_short_lowercase_label(
    environment: pytest.MonkeyPatch, version: str
) -> None:
    environment.setenv("PRIVACY_NOTICE_VERSION", version)

    with pytest.raises(ValidationError, match="privacy_notice_version"):
        Settings()


def test_deployed_environments_serve_public_media_over_https(
    environment: pytest.MonkeyPatch,
) -> None:
    _deployed(environment).setenv("MEDIA_PUBLIC_BASE_URL", "http://media.example.in")

    with pytest.raises(ValidationError, match="MEDIA_PUBLIC_BASE_URL"):
        Settings()


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({"S3_ACCESS_KEY_ID": "key"}, "S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY together"),
        (
            {"MEDIA_PRIVATE_BUCKET": "one-bucket", "MEDIA_PUBLIC_BUCKET": "one-bucket"},
            "must differ",
        ),
        ({"MEDIA_PUBLIC_BUCKET": "Not_A_Bucket"}, "media_public_bucket"),
        ({"MEDIA_PUBLIC_BASE_URL": "media.example.in"}, "media_public_base_url"),
    ],
)
def test_storage_settings_are_checked(
    environment: pytest.MonkeyPatch, variables: dict[str, str], message: str
) -> None:
    for name, value in variables.items():
        environment.setenv(name, value)

    with pytest.raises(ValidationError, match=message):
        Settings()
