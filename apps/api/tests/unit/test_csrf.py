import re
import uuid
from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import (
    EXEMPT_PREFIXES,
    UNSAFE_METHODS,
    is_valid_csrf_token,
    issue_csrf_token,
)
from app.main import create_app
from tests.conftest import TEST_SECRET_KEY, build_settings

type Requester = Callable[..., httpx.Response]

SECRET = TEST_SECRET_KEY.encode()
SESSION_A = "a" * 43
SESSION_B = "b" * 43


def test_a_token_is_valid_only_for_the_session_it_was_issued_for() -> None:
    anonymous = issue_csrf_token(SECRET, None)
    bound = issue_csrf_token(SECRET, SESSION_A)

    assert is_valid_csrf_token(SECRET, anonymous, None)
    assert is_valid_csrf_token(SECRET, bound, SESSION_A)
    assert not is_valid_csrf_token(SECRET, bound, SESSION_B)
    assert not is_valid_csrf_token(SECRET, bound, None)
    assert not is_valid_csrf_token(SECRET, anonymous, SESSION_A)


def test_tokens_are_random_and_signed_with_the_secret_key() -> None:
    token = issue_csrf_token(SECRET, None)
    nonce, _, signature = token.partition(".")

    assert token != issue_csrf_token(SECRET, None)
    assert not is_valid_csrf_token(b"another-secret-key-0123456789abcdef", token, None)
    assert not is_valid_csrf_token(SECRET, f"{nonce}x.{signature}", None)
    assert not is_valid_csrf_token(SECRET, f"{nonce}.{signature[:-1]}", None)


@pytest.mark.parametrize("token", ["", ".", "nonce", "nonce.", ".signature", "a.b.c"])
def test_malformed_tokens_are_invalid(token: str) -> None:
    assert not is_valid_csrf_token(SECRET, token, None)


@pytest.fixture
def app() -> FastAPI:
    app = create_app(build_settings())

    @app.get("/test/read")
    async def read() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/test/write")
    async def write() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/webhooks/test-provider")
    async def webhook() -> dict[str, bool]:
        return {"ok": True}

    return app


def _browser(
    token: str | None, *, cookie_token: str | None = None, session: str | None = None
) -> dict[str, str]:
    cookies = []
    if cookie_token is not None:
        cookies.append(f"{CSRF_COOKIE}={cookie_token}")
    if session is not None:
        cookies.append(f"{SESSION_COOKIE}={session}")
    headers = {"Cookie": "; ".join(cookies)} if cookies else {}
    if token is not None:
        headers[CSRF_HEADER] = token
    return headers


def test_reads_need_no_token(app: FastAPI, request_app: Requester) -> None:
    assert request_app(app, "GET", "/test/read").status_code == 200


def test_a_write_with_the_cookies_token_in_the_header_passes(
    app: FastAPI, request_app: Requester
) -> None:
    token = issue_csrf_token(SECRET, SESSION_A)

    response = request_app(
        app, "POST", "/test/write", headers=_browser(token, cookie_token=token, session=SESSION_A)
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "case",
    ["no header", "no cookie", "header differs from cookie", "token of another session"],
)
def test_writes_without_a_matching_token_are_refused(
    app: FastAPI, request_app: Requester, case: str
) -> None:
    token = issue_csrf_token(SECRET, SESSION_A)
    other = issue_csrf_token(SECRET, SESSION_A)
    headers = {
        "no header": _browser(None, cookie_token=token, session=SESSION_A),
        "no cookie": _browser(token, session=SESSION_A),
        "header differs from cookie": _browser(token, cookie_token=other, session=SESSION_A),
        # A cookie planted by a sibling subdomain, or kept from an earlier session.
        "token of another session": _browser(token, cookie_token=token, session=SESSION_B),
    }[case]

    response = request_app(app, "POST", "/test/write", headers=headers)

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "CSRF_TOKEN_INVALID"


def test_provider_webhooks_are_exempt(app: FastAPI, request_app: Requester) -> None:
    assert request_app(app, "POST", "/v1/webhooks/test-provider").status_code == 200


def test_unknown_routes_and_methods_still_answer_404_and_405(
    app: FastAPI, request_app: Requester
) -> None:
    assert request_app(app, "POST", "/test/nowhere").status_code == 404
    assert request_app(app, "DELETE", "/healthz").status_code == 405


def test_every_state_changing_route_refuses_a_request_without_a_token(
    request_app: Requester,
) -> None:
    # Deny by default: no route of the real application may skip the check. FastAPI keeps
    # included routers nested, so walk their effective routes as its OpenAPI generator does.
    app = create_app(build_settings())
    checked = 0
    for route in iter_route_contexts(app.routes):
        if not isinstance(route.original_route, APIRoute) or route.path is None:
            continue
        if route.path.startswith(EXEMPT_PREFIXES):
            continue
        path = re.sub(r"\{[^}]+\}", str(uuid.uuid7()), route.path)
        for method in sorted((route.methods or set()) & UNSAFE_METHODS):
            response = request_app(app, method, path)
            assert (response.status_code, response.json()["code"]) == (
                403,
                "CSRF_TOKEN_INVALID",
            ), f"{method} {route.path}"
            checked += 1

    assert checked >= 3
