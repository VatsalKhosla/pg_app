"""Sessions end to end: cookies, sliding expiry, rotation, sign-out and CSRF (step 1.1).

Each test runs the real app against PostgreSQL with a frozen clock, signs users in through the
session service (OTP sign-in arrives in step 1.2) and then talks to the routes over HTTP.
"""

import asyncio
import hashlib
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from app.config import Settings
from app.core.actor import Role
from app.core.clock import FrozenClock
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import issue_csrf_token
from app.main import create_app
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.models import User, UserSession
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import SessionService, delete_finished_sessions
from tests.conftest import TEST_SECRET_KEY

pytestmark = pytest.mark.integration

type SettingsFactory = Callable[..., Settings]
type Scenario = Callable[[FastAPI, httpx.AsyncClient], Awaitable[Any]]

START = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(START)


@pytest.fixture
def run(
    make_settings: SettingsFactory, database_url: str, clock: FrozenClock
) -> Callable[..., Any]:
    """Run a scenario against the app (lifespan open) and an HTTPS client for it."""

    def run_scenario(scenario: Scenario, **settings: object) -> Any:
        app = create_app(make_settings(database_url=database_url, **settings), clock=clock)

        async def wrapped() -> Any:
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="https://api.test"
                ) as client:
                    return await scenario(app, client)

        return asyncio.run(wrapped())

    return run_scenario


def _new_phone() -> str:
    return f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"


async def _add_user(app: FastAPI, *roles: Role) -> int:
    async with app.state.sessionmaker() as db, db.begin():
        user = await UserRepository(db).add(phone_e164=_new_phone(), roles=roles or (Role.STUDENT,))
        return user.id


async def _sign_in(
    app: FastAPI,
    user_id: int,
    *,
    kind: SessionKind = SessionKind.USER,
    user_agent: str | None = "Mozilla/5.0 (Linux; Android 14) Chrome/140",
    replacing: str | None = None,
) -> str:
    async with app.state.sessionmaker() as db:
        issued = await SessionService(db, app.state.clock).start(
            user_id,
            kind=kind,
            ip_address="203.0.113.7",
            user_agent=user_agent,
            replacing=replacing,
        )
        return issued.token


def _as(session_token: str | None, *, csrf: bool = False) -> dict[str, str]:
    """Headers of a browser holding ``session_token``; with ``csrf``, a valid CSRF token too."""
    cookies = [] if session_token is None else [f"{SESSION_COOKIE}={session_token}"]
    headers: dict[str, str] = {}
    if csrf:
        token = issue_csrf_token(TEST_SECRET_KEY.encode(), session_token)
        cookies.append(f"{CSRF_COOKIE}={token}")
        headers[CSRF_HEADER] = token
    if cookies:
        headers["Cookie"] = "; ".join(cookies)
    return headers


def _set_cookies(response: httpx.Response) -> dict[str, str]:
    """Each cookie the response sets, by name, with its attributes."""
    return {header.split("=", 1)[0]: header for header in response.headers.get_list("set-cookie")}


def test_a_session_cookie_identifies_the_user(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        user_id = await _add_user(app, Role.STUDENT, Role.PARENT)
        token = await _sign_in(app, user_id)

        response = await client.get("/v1/me", headers=_as(token))

        assert response.status_code == 200
        body = response.json()
        assert body["phone"].startswith("+91")
        assert body["roles"] == ["parent", "student"]
        assert set(body) == {"id", "phone", "email", "name", "roles"}

    run(scenario)


def test_only_a_hash_of_the_token_is_stored(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        token = await _sign_in(app, await _add_user(app))

        async with app.state.sessionmaker() as db:
            row = await db.scalar(
                select(UserSession).where(
                    UserSession.token_hash == hashlib.sha256(token.encode()).digest()
                )
            )

        assert row is not None
        assert token.encode() not in row.token_hash
        assert len(token) == 43  # 256 random bits, base64url

    run(scenario)


def test_requests_without_a_live_session_answer_401(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        never_issued = secrets.token_urlsafe(32)
        ended = await _sign_in(app, await _add_user(app))
        async with app.state.sessionmaker() as db:
            await SessionService(db, app.state.clock).end(ended)

        for headers in ({}, _as(never_issued), _as(ended)):
            response = await client.get("/v1/me", headers=headers)
            assert (response.status_code, response.json()["code"]) == (401, "UNAUTHENTICATED")

    run(scenario)


def test_activity_slides_a_user_session_and_30_idle_days_end_it(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        token = await _sign_in(app, await _add_user(app))

        clock.advance(timedelta(minutes=5))
        quiet = await client.get("/v1/me", headers=_as(token))
        clock.advance(timedelta(days=29))
        active = await client.get("/v1/me", headers=_as(token))
        clock.advance(timedelta(days=29, hours=23))
        still_signed_in = await client.get("/v1/me", headers=_as(token))
        clock.advance(timedelta(days=30, seconds=1))
        expired = await client.get("/v1/me", headers=_as(token))

        # Within 10 minutes of the last activity nothing moves, so no cookie goes out.
        assert quiet.status_code == 200
        assert SESSION_COOKIE not in _set_cookies(quiet)
        # Later activity moves the expiry and sends the cookie again with a fresh lifetime.
        assert active.status_code == still_signed_in.status_code == 200
        refreshed = _set_cookies(active)[SESSION_COOKIE]
        assert f"{SESSION_COOKIE}={token};" in refreshed
        assert f"Max-Age={30 * 24 * 3600}" in refreshed
        for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
            assert attribute in refreshed
        assert expired.status_code == 401

    run(scenario)


def test_staff_sessions_end_12_hours_after_sign_in_however_active(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        token = await _sign_in(app, await _add_user(app, Role.OPS), kind=SessionKind.STAFF)

        clock.advance(timedelta(hours=11, minutes=59))
        busy = await client.get("/v1/me", headers=_as(token))
        clock.advance(timedelta(minutes=2))
        over = await client.get("/v1/me", headers=_as(token))

        assert busy.status_code == 200
        assert over.status_code == 401

    run(scenario)


def test_the_session_cookie_names_the_parent_domain_when_configured(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        token = await _sign_in(app, await _add_user(app))
        clock.advance(timedelta(hours=1))

        response = await client.get("/v1/me", headers=_as(token))

        assert "Domain=.example.test" in _set_cookies(response)[SESSION_COOKIE]

    run(scenario, session_cookie_domain=".example.test")


def test_rotation_replaces_the_token_and_keeps_the_session(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        old = await _sign_in(app, await _add_user(app))
        before = (await client.get("/v1/me/sessions", headers=_as(old))).json()

        async with app.state.sessionmaker() as db:
            rotated = await SessionService(db, app.state.clock).rotate(old)
        assert rotated is not None
        after = (await client.get("/v1/me/sessions", headers=_as(rotated.token))).json()

        assert (await client.get("/v1/me", headers=_as(old))).status_code == 401
        assert (await client.get("/v1/me", headers=_as(rotated.token))).status_code == 200
        assert [s["id"] for s in after["sessions"]] == [s["id"] for s in before["sessions"]]

    run(scenario)


def test_signing_in_again_ends_the_session_it_replaces(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        # A token planted in the browser before sign-in must never become a signed-in session.
        user_id = await _add_user(app)
        planted = await _sign_in(app, user_id)
        fresh = await _sign_in(app, user_id, replacing=planted)

        assert (await client.get("/v1/me", headers=_as(planted))).status_code == 401
        assert (await client.get("/v1/me", headers=_as(fresh))).status_code == 200

    run(scenario)


def test_logout_ends_the_session_and_clears_both_cookies(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        token = await _sign_in(app, await _add_user(app))

        response = await client.post("/v1/auth/logout", headers=_as(token, csrf=True))
        again = await client.post("/v1/auth/logout", headers=_as(token, csrf=True))

        assert response.status_code == 204
        cleared = _set_cookies(response)
        assert "Max-Age=0" in cleared[SESSION_COOKIE]
        assert "Max-Age=0" in cleared[CSRF_COOKIE]
        assert (await client.get("/v1/me", headers=_as(token))).status_code == 401
        assert again.status_code == 204

    run(scenario)


def test_a_logout_without_a_valid_csrf_token_is_refused_and_changes_nothing(
    run: Callable[..., Any],
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        token = await _sign_in(app, await _add_user(app))
        other = await _sign_in(app, await _add_user(app))
        # A token issued for another session (planted by a sibling subdomain, say).
        foreign = _as(other, csrf=True)
        forged = {
            "Cookie": f"{SESSION_COOKIE}={token}; " + foreign["Cookie"].split("; ")[1],
            CSRF_HEADER: foreign[CSRF_HEADER],
        }

        missing = await client.post("/v1/auth/logout", headers=_as(token))
        mismatched = await client.post("/v1/auth/logout", headers=forged)

        for response in (missing, mismatched):
            assert (response.status_code, response.json()["code"]) == (403, "CSRF_TOKEN_INVALID")
        assert (await client.get("/v1/me", headers=_as(token))).status_code == 200

    run(scenario)


def test_logout_everywhere_ends_every_session_of_the_user_and_no_one_elses(
    run: Callable[..., Any],
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        user_id = await _add_user(app)
        phone, laptop = await _sign_in(app, user_id), await _sign_in(app, user_id)
        someone_else = await _sign_in(app, await _add_user(app))

        response = await client.post("/v1/auth/logout-everywhere", headers=_as(phone, csrf=True))

        assert response.status_code == 204
        assert "Max-Age=0" in _set_cookies(response)[SESSION_COOKIE]
        assert (await client.get("/v1/me", headers=_as(phone))).status_code == 401
        assert (await client.get("/v1/me", headers=_as(laptop))).status_code == 401
        assert (await client.get("/v1/me", headers=_as(someone_else))).status_code == 200

    run(scenario)


def test_the_session_list_shows_live_sessions_and_marks_this_one(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        user_id = await _add_user(app)
        phone = await _sign_in(app, user_id, user_agent="Phone browser")
        clock.advance(timedelta(minutes=1))
        laptop = await _sign_in(app, user_id, user_agent="Laptop browser")
        ended = await _sign_in(app, user_id, user_agent="Old tablet")
        async with app.state.sessionmaker() as db:
            await SessionService(db, app.state.clock).end(ended)

        listed = (await client.get("/v1/me/sessions", headers=_as(phone))).json()["sessions"]

        assert {(s["userAgent"], s["current"]) for s in listed} == {
            ("Phone browser", True),
            ("Laptop browser", False),
        }
        assert laptop not in str(listed)
        assert {"id", "current", "startedAt", "lastSeenAt", "expiresAt", "userAgent"} == set(
            listed[0]
        )

    run(scenario)


def test_ending_another_device_signs_only_that_device_out(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        user_id = await _add_user(app)
        phone = await _sign_in(app, user_id, user_agent="Phone browser")
        laptop = await _sign_in(app, user_id, user_agent="Laptop browser")
        listed = (await client.get("/v1/me/sessions", headers=_as(phone))).json()["sessions"]
        laptop_id = next(s["id"] for s in listed if s["userAgent"] == "Laptop browser")

        response = await client.delete(
            f"/v1/me/sessions/{laptop_id}", headers=_as(phone, csrf=True)
        )

        assert response.status_code == 204
        assert SESSION_COOKIE not in _set_cookies(response)
        assert (await client.get("/v1/me", headers=_as(laptop))).status_code == 401
        assert (await client.get("/v1/me", headers=_as(phone))).status_code == 200

    run(scenario)


def test_another_users_session_answers_404_and_keeps_working(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        mine = await _sign_in(app, await _add_user(app))
        theirs = await _sign_in(app, await _add_user(app))
        their_id = (await client.get("/v1/me/sessions", headers=_as(theirs))).json()["sessions"][0][
            "id"
        ]

        response = await client.delete(f"/v1/me/sessions/{their_id}", headers=_as(mine, csrf=True))

        assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
        assert (await client.get("/v1/me", headers=_as(theirs))).status_code == 200

    run(scenario)


def test_a_suspended_user_is_signed_out(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        user_id = await _add_user(app)
        token = await _sign_in(app, user_id)
        async with app.state.sessionmaker() as db, db.begin():
            await db.execute(update(User).where(User.id == user_id).values(status="suspended"))

        assert (await client.get("/v1/me", headers=_as(token))).status_code == 401

    run(scenario)


def test_finished_sessions_are_deleted_30_days_after_they_end(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, _client: httpx.AsyncClient) -> None:
        user_id = await _add_user(app)
        long_ended, recently_ended, live = (
            await _sign_in(app, user_id),
            await _sign_in(app, user_id),
            await _sign_in(app, user_id),
        )
        async with app.state.sessionmaker() as db:
            await SessionService(db, app.state.clock).end(long_ended)
        clock.advance(timedelta(days=2))
        async with app.state.sessionmaker() as db:
            await SessionService(db, app.state.clock).end(recently_ended)

        clock.advance(timedelta(days=29))
        async with app.state.sessionmaker() as db, db.begin():
            deleted = await delete_finished_sessions(db, app.state.clock)
            remaining = await db.scalars(
                select(UserSession.token_hash).where(UserSession.user_id == user_id)
            )
            left = set(remaining)

        def digest(token: str) -> bytes:
            return hashlib.sha256(token.encode()).digest()

        assert deleted >= 1
        assert digest(long_ended) not in left
        assert {digest(recently_ended), digest(live)} <= left

    run(scenario)
