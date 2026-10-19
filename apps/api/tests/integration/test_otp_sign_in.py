"""Phone sign-in end to end (step 1.2): request a code, check it, get a session.

The app runs against PostgreSQL and Valkey with a frozen clock. A recording sender stands in for
SMS, so each test sees exactly the codes that would have gone out.
"""

import asyncio
import secrets
import uuid
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
from app.modules.identity.models import OtpChallenge, User
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import SessionService, delete_old_challenges
from tests.conftest import TEST_SECRET_KEY

pytestmark = pytest.mark.integration

type SettingsFactory = Callable[..., Settings]
type Scenario = Callable[[FastAPI, httpx.AsyncClient], Awaitable[Any]]

START = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)


class RecordingSender:
    """Keeps the codes that would have been texted, by phone."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone_e164: str, code: str) -> None:
        self.sent.append((phone_e164, code))

    def last_code(self) -> str:
        return self.sent[-1][1]


class FailingSender:
    async def send(self, phone_e164: str, code: str) -> None:
        msg = "SMS gateway timed out"
        raise TimeoutError(msg)


class RefusingHumanCheck:
    """Refuses every token, keeping what each check was asked."""

    def __init__(self) -> None:
        self.checked: list[tuple[str, str | None, str]] = []

    async def verify(self, token: str, *, remote_ip: str | None, action: str) -> bool:
        self.checked.append((token, remote_ip, action))
        return False


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(START)


@pytest.fixture
def sender() -> RecordingSender:
    return RecordingSender()


@pytest.fixture
def run(
    make_settings: SettingsFactory,
    database_url: str,
    valkey_url: str,
    clock: FrozenClock,
    sender: RecordingSender,
) -> Callable[..., Any]:
    """Run a scenario against the app (lifespan open, recording sender in place)."""

    def run_scenario(scenario: Scenario, **settings: object) -> Any:
        app = create_app(
            make_settings(database_url=database_url, redis_url=valkey_url, **settings),
            clock=clock,
        )

        async def wrapped() -> Any:
            async with app.router.lifespan_context(app):
                if app.state.otp_sender.__class__.__name__ == "ConsoleOtpSender":
                    app.state.otp_sender = sender
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="https://api.test"
                ) as client:
                    return await scenario(app, client)

        return asyncio.run(wrapped())

    return run_scenario


def _new_mobile() -> str:
    """A random Indian mobile number, ten digits, so tests never share a phone."""
    return str(6_000_000_000 + secrets.randbelow(4_000_000_000))


def _browser(session_token: str | None = None) -> dict[str, str]:
    """Headers of a browser with a valid CSRF token (bound to its session, if it has one)."""
    token = issue_csrf_token(TEST_SECRET_KEY.encode(), session_token)
    cookies = [f"{CSRF_COOKIE}={token}"]
    if session_token is not None:
        cookies.append(f"{SESSION_COOKIE}={session_token}")
    return {CSRF_HEADER: token, "Cookie": "; ".join(cookies)}


async def _request_code(
    client: httpx.AsyncClient, phone: str, *, headers: dict[str, str] | None = None
) -> httpx.Response:
    return await client.post(
        "/v1/auth/otp/request",
        json={"phone": phone, "humanCheckToken": "XXXX.DUMMY.TOKEN.XXXX"},
        headers=headers or _browser(),
    )


async def _verify(
    client: httpx.AsyncClient,
    challenge_id: str,
    code: str,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.post(
        "/v1/auth/otp/verify",
        json={"challengeId": challenge_id, "code": code},
        headers=headers or _browser(),
    )


def _cookies_set(response: httpx.Response) -> dict[str, str]:
    return {header.split("=", 1)[0]: header for header in response.headers.get_list("set-cookie")}


def _cookie_value(set_cookie: str) -> str:
    return set_cookie.split(";", 1)[0].split("=", 1)[1]


def test_signing_in_with_a_phone_code_end_to_end(
    run: Callable[..., Any], sender: RecordingSender
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()

        requested = await _request_code(client, f"0{mobile[:5]} {mobile[5:]}")
        assert requested.status_code == 202
        challenge = requested.json()
        assert set(challenge) == {"challengeId", "expiresAt", "resendAfter"}
        assert sender.sent == [(f"+91{mobile}", sender.last_code())]
        assert len(sender.last_code()) == 6

        signed_in = await _verify(client, challenge["challengeId"], sender.last_code())

        assert signed_in.status_code == 200
        body = signed_in.json()
        assert body["newUser"] is True
        assert body["user"]["phone"] == f"+91{mobile}"
        assert body["user"]["roles"] == []
        cookies = _cookies_set(signed_in)
        session_cookie = cookies[SESSION_COOKIE]
        for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
            assert attribute in session_cookie
        assert f"Max-Age={30 * 24 * 3600}" in session_cookie
        assert "HttpOnly" not in cookies[CSRF_COOKIE]
        assert _cookie_value(cookies[CSRF_COOKIE]) == body["csrfToken"]

        # The new session works, and so does the CSRF token bound to it.
        session = _cookie_value(session_cookie)
        me = await client.get("/v1/me", headers={"Cookie": f"{SESSION_COOKIE}={session}"})
        assert me.json()["id"] == body["user"]["id"]
        logged_out = await client.post(
            "/v1/auth/logout",
            headers={
                CSRF_HEADER: body["csrfToken"],
                "Cookie": f"{SESSION_COOKIE}={session}; {CSRF_COOKIE}={body['csrfToken']}",
            },
        )
        assert logged_out.status_code == 204

    run(scenario)


def test_signing_in_again_finds_the_same_account(
    run: Callable[..., Any], sender: RecordingSender, clock: FrozenClock
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        first = await _request_code(client, mobile)
        user = (await _verify(client, first.json()["challengeId"], sender.last_code())).json()
        clock.advance(timedelta(minutes=1))

        second = await _request_code(client, f"+91 {mobile}")
        again = (await _verify(client, second.json()["challengeId"], sender.last_code())).json()

        assert again["newUser"] is False
        assert again["user"]["id"] == user["user"]["id"]

    run(scenario)


def test_signing_in_ends_the_session_this_browser_had(
    run: Callable[..., Any], sender: RecordingSender
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        async with app.state.sessionmaker() as db, db.begin():
            user = await UserRepository(db).add(phone_e164=f"+91{mobile}", roles=())
        async with app.state.sessionmaker() as db:
            earlier = await SessionService(db, app.state.clock).start(
                user.id, kind=SessionKind.USER, ip_address=None, user_agent=None
            )

        requested = await _request_code(client, mobile, headers=_browser(earlier.token))
        await _verify(
            client,
            requested.json()["challengeId"],
            sender.last_code(),
            headers=_browser(earlier.token),
        )

        stale = await client.get("/v1/me", headers={"Cookie": f"{SESSION_COOKIE}={earlier.token}"})
        assert stale.status_code == 401

    run(scenario)


def test_five_wrong_codes_lock_the_challenge_and_the_sixth_try_fails_even_if_right(
    run: Callable[..., Any], sender: RecordingSender
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        challenge_id = (await _request_code(client, _new_mobile())).json()["challengeId"]
        right = sender.last_code()
        wrong = f"{(int(right) + 1) % 1_000_000:06d}"

        answers = [await _verify(client, challenge_id, wrong) for _ in range(5)]
        sixth = await _verify(client, challenge_id, right)

        assert [(a.status_code, a.json()["code"]) for a in answers] == [(400, "OTP_INVALID")] * 5
        assert [a.json()["detail"] for a in answers] == [
            "4 attempts left.",
            "3 attempts left.",
            "2 attempts left.",
            "1 attempts left.",
            "No attempts left; ask for a new code.",
        ]
        assert (sixth.status_code, sixth.json()["code"]) == (400, "OTP_LOCKED")

    run(scenario)


def test_a_code_expires_after_five_minutes(
    run: Callable[..., Any], sender: RecordingSender, clock: FrozenClock
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        challenge_id = (await _request_code(client, _new_mobile())).json()["challengeId"]
        clock.advance(timedelta(minutes=5))

        response = await _verify(client, challenge_id, sender.last_code())

        assert (response.status_code, response.json()["code"]) == (400, "OTP_EXPIRED")

    run(scenario)


def test_a_new_code_replaces_the_previous_one(
    run: Callable[..., Any], sender: RecordingSender, clock: FrozenClock
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        old_challenge = (await _request_code(client, mobile)).json()["challengeId"]
        old_code = sender.last_code()
        clock.advance(timedelta(seconds=30))
        new_challenge = (await _request_code(client, mobile)).json()["challengeId"]

        old = await _verify(client, old_challenge, old_code)
        new = await _verify(client, new_challenge, sender.last_code())

        assert (old.status_code, old.json()["code"]) == (400, "OTP_INVALID")
        assert new.status_code == 200

    run(scenario)


def test_a_new_code_can_be_sent_only_30_seconds_after_the_last(
    run: Callable[..., Any], clock: FrozenClock, sender: RecordingSender
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        await _request_code(client, mobile)
        clock.advance(timedelta(seconds=10))

        too_soon = await _request_code(client, mobile)
        clock.advance(timedelta(seconds=20))
        in_time = await _request_code(client, mobile)

        assert (too_soon.status_code, too_soon.json()["code"]) == (429, "OTP_RESEND_TOO_SOON")
        assert too_soon.headers["Retry-After"] == "20"
        assert in_time.status_code == 202
        assert len(sender.sent) == 2

    run(scenario)


def test_a_phone_gets_at_most_five_codes_an_hour(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        statuses = []
        for _ in range(6):
            statuses.append((await _request_code(client, mobile)).status_code)
            clock.advance(timedelta(seconds=31))
        limited = await _request_code(client, mobile)
        clock.advance(timedelta(hours=1))
        after_an_hour = await _request_code(client, mobile)

        assert statuses == [202, 202, 202, 202, 202, 429]
        assert (limited.status_code, limited.json()["code"]) == (429, "RATE_LIMITED")
        assert int(limited.headers["Retry-After"]) > 0
        assert after_an_hour.status_code == 202

    run(scenario)


def test_no_code_is_sent_unless_the_human_check_passes(
    run: Callable[..., Any], sender: RecordingSender
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        human_check = RefusingHumanCheck()
        app.state.human_check = human_check

        response = await _request_code(client, _new_mobile())

        assert (response.status_code, response.json()["code"]) == (400, "HUMAN_CHECK_FAILED")
        assert sender.sent == []
        # The widget's token, checked for the sign-in form, from the caller's address.
        assert human_check.checked == [("XXXX.DUMMY.TOKEN.XXXX", "127.0.0.1", "otp_request")]

    run(scenario)


def test_a_number_that_isnt_an_indian_mobile_is_a_field_error(run: Callable[..., Any]) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        response = await _request_code(client, "+1 415 555 0123")

        assert response.status_code == 422
        error = response.json()["errors"][0]
        assert (error["pointer"], error["code"]) == ("/phone", "phone_invalid")
        assert "415" not in response.text

    run(scenario)


def test_a_failed_sms_can_be_retried_at_once(
    run: Callable[..., Any], sender: RecordingSender
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        app.state.otp_sender = FailingSender()
        failed = await _request_code(client, mobile)
        app.state.otp_sender = sender
        retried = await _request_code(client, mobile)

        assert (failed.status_code, failed.json()["code"]) == (503, "SERVICE_UNAVAILABLE")
        assert retried.status_code == 202

    run(scenario)


def test_phone_sign_in_is_off_without_an_sms_provider(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()

        response = await _request_code(client, mobile)

        assert (response.status_code, response.json()["code"]) == (503, "SERVICE_UNAVAILABLE")
        assert response.json()["detail"] == "Signing in by phone isn't available yet."
        async with app.state.sessionmaker() as db:
            left = await db.scalars(
                select(OtpChallenge).where(OtpChallenge.phone_e164 == f"+91{mobile}")
            )
            assert left.all() == []

    run(scenario, otp_sender="unavailable")


def test_a_suspended_account_cant_sign_in(run: Callable[..., Any], sender: RecordingSender) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        async with app.state.sessionmaker() as db, db.begin():
            user = await UserRepository(db).add(phone_e164=f"+91{mobile}", roles=())
            await db.execute(update(User).where(User.id == user.id).values(status="suspended"))

        challenge_id = (await _request_code(client, mobile)).json()["challengeId"]
        response = await _verify(client, challenge_id, sender.last_code())

        assert (response.status_code, response.json()["code"]) == (403, "ACCOUNT_SUSPENDED")
        assert SESSION_COOKIE not in _cookies_set(response)

    run(scenario)


def test_staff_roles_never_come_with_a_phone_sign_in(
    run: Callable[..., Any], sender: RecordingSender
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        async with app.state.sessionmaker() as db, db.begin():
            await UserRepository(db).add(phone_e164=f"+91{mobile}", roles=(Role.OPS, Role.OWNER))

        challenge_id = (await _request_code(client, mobile)).json()["challengeId"]
        signed_in = await _verify(client, challenge_id, sender.last_code())
        session = _cookie_value(_cookies_set(signed_in)[SESSION_COOKIE])
        me = await client.get("/v1/me", headers={"Cookie": f"{SESSION_COOKIE}={session}"})

        assert signed_in.json()["user"]["roles"] == ["owner"]
        assert me.json()["roles"] == ["owner"]

    run(scenario)


def test_unknown_challenges_and_malformed_codes_are_refused(run: Callable[..., Any]) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        unknown = await _verify(client, str(uuid.uuid7()), "123456")
        malformed = await _verify(client, str(uuid.uuid7()), "12a456")

        assert (unknown.status_code, unknown.json()["code"]) == (400, "OTP_INVALID")
        assert (malformed.status_code, malformed.json()["code"]) == (422, "VALIDATION_ERROR")

    run(scenario)


def test_codes_are_stored_only_as_keyed_hashes(
    run: Callable[..., Any], sender: RecordingSender
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        challenge_id = (await _request_code(client, _new_mobile())).json()["challengeId"]

        async with app.state.sessionmaker() as db:
            stored = await db.scalar(
                select(OtpChallenge).where(OtpChallenge.public_id == uuid.UUID(challenge_id))
            )

        assert stored is not None
        assert sender.last_code() not in stored.code_hash
        assert len(stored.code_hash) == 32

    run(scenario)


def test_challenges_are_deleted_after_seven_days(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        old_phone, recent_phone = _new_mobile(), _new_mobile()
        await _request_code(client, old_phone)
        clock.advance(timedelta(days=3))
        await _request_code(client, recent_phone)
        clock.advance(timedelta(days=4, seconds=1))

        async with app.state.sessionmaker() as db, db.begin():
            await delete_old_challenges(db, app.state.clock)
            phones = set(await db.scalars(select(OtpChallenge.phone_e164)))

        assert f"+91{old_phone}" not in phones
        assert f"+91{recent_phone}" in phones

    run(scenario)
