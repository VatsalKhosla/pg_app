import uuid
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from fastapi import FastAPI, Request

from app.config import Settings
from app.core.security import API_CSP, HSTS
from app.main import create_app

type Requester = Callable[..., httpx.Response]
type SettingsFactory = Callable[..., Settings]

ALLOWED_ORIGIN = "http://localhost:3000"


def test_json_responses_carry_the_security_headers(
    make_settings: SettingsFactory, request_app: Requester
) -> None:
    headers = request_app(create_app(make_settings()), "GET", "/healthz").headers

    assert headers["content-security-policy"] == API_CSP
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cross-origin-opener-policy"] == "same-origin"
    assert headers["cross-origin-resource-policy"] == "same-site"
    assert "strict-transport-security" not in headers  # only when served over HTTPS


def test_deployed_environments_add_hsts_and_hide_the_interactive_docs(
    make_settings: SettingsFactory, request_app: Requester
) -> None:
    app = create_app(make_settings(app_env="production", cors_allowed_origins=()))

    assert request_app(app, "GET", "/healthz").headers["strict-transport-security"] == HSTS
    assert request_app(app, "GET", "/docs").status_code == 404
    assert request_app(app, "GET", "/openapi.json").status_code == 200


def test_the_interactive_docs_are_served_locally_without_the_strict_csp(
    make_settings: SettingsFactory, request_app: Requester
) -> None:
    response = request_app(create_app(make_settings()), "GET", "/docs")

    assert response.status_code == 200
    assert response.headers.get("content-security-policy") != API_CSP


def test_cors_allows_exactly_the_configured_origins(
    make_settings: SettingsFactory, request_app: Requester
) -> None:
    app = create_app(make_settings())

    allowed = request_app(app, "GET", "/healthz", headers={"Origin": ALLOWED_ORIGIN}).headers
    other = request_app(app, "GET", "/healthz", headers={"Origin": "https://evil.example"})

    assert allowed["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert allowed["access-control-allow-credentials"] == "true"
    assert "x-request-id" in allowed["access-control-expose-headers"].lower()
    assert "access-control-allow-origin" not in other.headers


def test_cors_preflight_allows_the_csrf_and_idempotency_headers(
    make_settings: SettingsFactory, request_app: Requester
) -> None:
    response = request_app(
        create_app(make_settings()),
        "OPTIONS",
        "/healthz",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, x-csrf-token, idempotency-key",
        },
    )

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert {"content-type", "x-csrf-token", "idempotency-key"} <= {
        header.strip() for header in allowed.split(",")
    }


@pytest.fixture
def echo_app(make_settings: SettingsFactory) -> FastAPI:
    app = create_app(make_settings(max_request_body_bytes=16))

    @app.post("/test/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    return app


def test_bodies_within_the_limit_are_accepted(
    echo_app: FastAPI, request_app: Requester, csrf_headers: dict[str, str]
) -> None:
    response = request_app(echo_app, "POST", "/test/echo", headers=csrf_headers, content=b"x" * 16)

    assert response.json() == {"bytes": 16}


def test_a_declared_oversize_body_is_refused_before_routing(
    echo_app: FastAPI, request_app: Requester
) -> None:
    response = request_app(echo_app, "POST", "/test/echo", content=b"x" * 17)

    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_a_streamed_oversize_body_is_refused_while_reading(
    echo_app: FastAPI, request_app: Requester, csrf_headers: dict[str, str]
) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(4):
            yield b"x" * 8  # 32 bytes in all, sent without a Content-Length

    response = request_app(echo_app, "POST", "/test/echo", headers=csrf_headers, content=chunks())

    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_a_well_formed_request_id_is_kept(
    make_settings: SettingsFactory, request_app: Requester
) -> None:
    response = request_app(
        create_app(make_settings()), "GET", "/healthz", headers={"X-Request-ID": "web-0192f6d4"}
    )

    assert response.headers["x-request-id"] == "web-0192f6d4"


@pytest.mark.parametrize("incoming", [None, "short", "has spaces in it", "x" * 65])
def test_otherwise_a_uuid7_request_id_is_generated(
    make_settings: SettingsFactory, request_app: Requester, incoming: str | None
) -> None:
    headers = {"X-Request-ID": incoming} if incoming else {}

    response = request_app(create_app(make_settings()), "GET", "/healthz", headers=headers)

    assert uuid.UUID(response.headers["x-request-id"]).version == 7
