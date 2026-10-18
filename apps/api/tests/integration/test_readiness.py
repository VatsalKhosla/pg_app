from collections.abc import Callable

import httpx
import pytest

from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration

type Requester = Callable[..., httpx.Response]
type SettingsFactory = Callable[..., Settings]


def test_ready_when_the_database_and_redis_answer(
    make_settings: SettingsFactory, request_app: Requester, postgres_url: str, valkey_url: str
) -> None:
    app = create_app(make_settings(database_url=postgres_url, redis_url=valkey_url))

    response = request_app(app, "GET", "/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


def test_not_ready_when_redis_rejects_the_password(
    make_settings: SettingsFactory, request_app: Requester, postgres_url: str, valkey_url: str
) -> None:
    wrong_password = valkey_url.replace("://:test@", "://:wrong-password@")
    app = create_app(make_settings(database_url=postgres_url, redis_url=wrong_password))

    response = request_app(app, "GET", "/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "ok", "redis": "unavailable"},
    }
