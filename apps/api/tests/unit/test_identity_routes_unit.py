from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI

from app.core.cookies import CSRF_COOKIE, SESSION_COOKIE
from app.core.csrf import is_valid_csrf_token
from app.main import create_app
from tests.conftest import TEST_SECRET_KEY, build_settings

type Requester = Callable[..., httpx.Response]


@pytest.fixture
def app() -> FastAPI:
    # Unit tests: the database is unreachable, so these cover what happens before it is asked.
    return create_app(build_settings())


def test_the_csrf_route_sets_a_readable_cookie_with_the_token_it_returns(
    app: FastAPI, request_app: Requester
) -> None:
    response = request_app(app, "GET", "/v1/auth/csrf")

    token = response.json()["csrfToken"]
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{CSRF_COOKIE}={token};")
    assert "Secure" in set_cookie
    assert "HttpOnly" not in set_cookie
    assert is_valid_csrf_token(TEST_SECRET_KEY.encode(), token, None)


def test_the_csrf_token_is_bound_to_the_browsers_session_cookie(
    app: FastAPI, request_app: Requester
) -> None:
    session = "s" * 43

    response = request_app(
        app, "GET", "/v1/auth/csrf", headers={"Cookie": f"{SESSION_COOKIE}={session}"}
    )

    token = response.json()["csrfToken"]
    assert is_valid_csrf_token(TEST_SECRET_KEY.encode(), token, session)
    assert not is_valid_csrf_token(TEST_SECRET_KEY.encode(), token, None)


@pytest.mark.parametrize("cookie", [None, "", "not-a-session-token", "x" * 200])
def test_signed_in_routes_answer_401_without_a_plausible_session_cookie(
    app: FastAPI, request_app: Requester, cookie: str | None
) -> None:
    headers = {} if cookie is None else {"Cookie": f"{SESSION_COOKIE}={cookie}"}

    response = request_app(app, "GET", "/v1/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
