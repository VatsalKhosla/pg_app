import json
from collections.abc import Callable

import httpx
import pytest

from app.config import BRAND_NAME, Settings
from app.main import create_app
from app.modules.system.domain.readiness import CheckState, overall_state
from app.modules.system.router import get_readiness_service
from app.modules.system.schemas import Readiness

type Requester = Callable[..., httpx.Response]
type SettingsFactory = Callable[..., Settings]


@pytest.mark.parametrize(
    ("checks", "expected"),
    [
        ({"database": "ok", "redis": "ok"}, "ok"),
        ({"database": "ok", "redis": "unavailable"}, "unavailable"),
        ({"database": "unavailable", "redis": "unavailable"}, "unavailable"),
        ({}, "unavailable"),  # nothing checked means not ready
    ],
)
def test_ready_only_when_every_check_passed(
    checks: dict[str, CheckState], expected: CheckState
) -> None:
    assert overall_state(checks) == expected


def test_healthz_reports_ok(make_settings: SettingsFactory, request_app: Requester) -> None:
    response = request_app(create_app(make_settings()), "GET", "/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class _FixedReadiness:
    def __init__(self, readiness: Readiness) -> None:
        self._readiness = readiness

    async def check(self) -> Readiness:
        return self._readiness


@pytest.mark.parametrize(("redis", "status_code"), [("ok", 200), ("unavailable", 503)])
def test_readyz_answers_503_unless_every_dependency_is_ok(
    make_settings: SettingsFactory, request_app: Requester, redis: CheckState, status_code: int
) -> None:
    checks: dict[str, CheckState] = {"database": "ok", "redis": redis}
    readiness = Readiness(status=overall_state(checks), checks=checks)
    app = create_app(make_settings())
    app.dependency_overrides[get_readiness_service] = lambda: _FixedReadiness(readiness)

    response = request_app(app, "GET", "/readyz")

    assert response.status_code == status_code
    assert response.json() == {"status": readiness.status, "checks": checks}


def test_readyz_reports_unreachable_dependencies_quickly(
    make_settings: SettingsFactory, request_app: Requester
) -> None:
    # The test settings point at a port where nothing listens.
    response = request_app(create_app(make_settings()), "GET", "/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "unavailable", "redis": "unavailable"},
    }


def test_openapi_is_served_and_describes_the_probes(
    make_settings: SettingsFactory, request_app: Requester
) -> None:
    schema = request_app(create_app(make_settings()), "GET", "/openapi.json").json()

    assert schema["info"]["title"] == f"{BRAND_NAME} API"
    assert {"/healthz", "/readyz"} <= set(schema["paths"])


def test_the_access_log_names_the_route_template_not_the_raw_path(
    make_settings: SettingsFactory, request_app: Requester, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app(make_settings())

    @app.get("/test/bookings/{code}")
    async def booking(code: str) -> dict[str, str]:
        return {"code": code}

    request_app(app, "GET", "/test/bookings/BK-7F3K2Q9M")

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line[:1] == "{"]
    access = [line for line in lines if line.get("event") == "request"][-1]
    assert access["route"] == "/test/bookings/{code}"
    assert (access["method"], access["status"]) == ("GET", 200)
    assert "BK-7F3K2Q9M" not in json.dumps(access)


@pytest.mark.parametrize(
    ("path", "route"), [("/openapi.json", "/openapi.json"), ("/no-such-route", "unmatched")]
)
def test_the_access_log_names_fixed_routes_and_marks_unknown_ones(
    make_settings: SettingsFactory,
    request_app: Requester,
    capsys: pytest.CaptureFixture[str],
    path: str,
    route: str,
) -> None:
    request_app(create_app(make_settings()), "GET", path)

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line[:1] == "{"]
    assert [line for line in lines if line.get("event") == "request"][-1]["route"] == route
