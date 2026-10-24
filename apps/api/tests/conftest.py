"""Shared fixtures: settings that ignore the developer's environment, and an in-process client."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from hypothesis import settings as hypothesis_settings
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.config import Settings
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER
from app.core.csrf import issue_csrf_token

# Property tests: 200 cases per property locally, 10,000 in CI (HYPOTHESIS_PROFILE=ci), as the
# build plan asks for the money and pricing invariants.
hypothesis_settings.register_profile("dev", max_examples=200, deadline=None)
hypothesis_settings.register_profile("ci", max_examples=10_000, deadline=None)
hypothesis_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

# Nothing listens on port 9 (discard): unit tests never reach a real database or Redis.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://test:test@127.0.0.1:9/test"
UNREACHABLE_REDIS_URL = "redis://:test@127.0.0.1:9/0"
TEST_SECRET_KEY = "test-only-secret-key-0123456789abcdef"
# The privacy notice version tests run with: the settings' default.
NOTICE_VERSION = Settings.model_fields["privacy_notice_version"].default


class IsolatedSettings(Settings):
    """Settings built only from the values given: the environment and .env are ignored, so a
    developer's real configuration (a Sentry DSN, say) can never leak into a test."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def build_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "log_format": "json",
        "database_url": UNREACHABLE_DATABASE_URL,
        "redis_url": UNREACHABLE_REDIS_URL,
        "secret_key": TEST_SECRET_KEY,
        "cors_allowed_origins": ("http://localhost:3000",),
        # Signing needs no network; anything that does reach storage fails fast.
        "s3_endpoint_url": "http://127.0.0.1:9",
        "s3_access_key_id": "test",
        "s3_secret_access_key": "test-secret",
    }
    values.update(overrides)
    return IsolatedSettings.model_validate(values)


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    return build_settings


@pytest.fixture
def csrf_headers() -> dict[str, str]:
    """What a browser without a session sends to pass the CSRF check: the token in the
    X-CSRF-Token header and in its cookie (app/core/csrf.py)."""
    token = issue_csrf_token(TEST_SECRET_KEY.encode(), None)
    return {CSRF_HEADER: token, "Cookie": f"{CSRF_COOKIE}={token}"}


async def _with_client[T](app: FastAPI, interact: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
            return await interact(client)


@pytest.fixture
def request_app() -> Callable[..., httpx.Response]:
    """Send one request to ``app`` in-process, inside the app's lifespan."""

    def request(app: FastAPI, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return asyncio.run(_with_client(app, lambda client: client.request(method, path, **kwargs)))

    return request
