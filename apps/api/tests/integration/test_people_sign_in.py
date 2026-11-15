"""Signing in by email and with Google, for anyone (ADR 0068), and switching phone codes off.

The app runs against PostgreSQL and Valkey with a frozen clock. A recording mailbox stands in for
email, and a fake Google for the real one (tests/google.py).
"""

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.config import Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from app.core.clock import FrozenClock
from app.core.cookies import GOOGLE_LOGIN_COOKIE, SESSION_COOKIE, STAFF_LOGIN_COOKIE
from app.main import create_app
from app.modules.identity.domain.otp import EMAIL_CODE_TTL, RESEND_COOLDOWN
from app.modules.identity.domain.staff import GoogleAccount, IdentityProvider
from app.modules.identity.errors import EmailTakenError
from app.modules.identity.models import OtpChallenge, User, UserIdentity
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import Accounts
from app.modules.identity.service.google_login import LOGIN_TTL
from tests.conftest import NOTICE_VERSION
from tests.google import Browser, FakeGoogle

pytestmark = pytest.mark.integration

type SettingsFactory = Callable[..., Settings]
type Scenario = Callable[[FastAPI, Browser], Awaitable[Any]]

START = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)
SITE = "https://www.example.in"
CALLBACK = "/v1/auth/staff/google/callback"
CONSENT: Final = {"noticeVersion": NOTICE_VERSION, "purposes": ["account"]}


class RecordingMail:
    """The codes that would have been emailed, by address, as a real mail server sends them."""

    shows_code = False
    available = True

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, email: str, code: str) -> None:
        self.sent.append((email, code))


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(START)


@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture
def mail() -> RecordingMail:
    return RecordingMail()


@pytest.fixture
def run(
    make_settings: SettingsFactory,
    database_url: str,
    valkey_url: str,
    *,
    clock: FrozenClock,
    google: FakeGoogle,
    mail: RecordingMail,
) -> Callable[..., Any]:
    """Run a scenario against the app (lifespan open; the recording mailbox and the fake Google in
    place unless ``fakes`` is False) from a client address of its own."""

    def run_scenario(scenario: Scenario, *, fakes: bool = True, **settings: object) -> Any:
        app = create_app(
            make_settings(
                database_url=database_url,
                redis_url=valkey_url,
                **({"site_url": SITE} | settings),
            ),
            clock=clock,
        )
        address = f"10.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}"

        async def wrapped() -> Any:
            async with app.router.lifespan_context(app):
                if fakes:
                    app.state.email_codes = mail
                    app.state.google_sign_in = google
                transport = httpx.ASGITransport(app=app, client=(address, 50_000))
                async with httpx.AsyncClient(
                    transport=transport, base_url="https://api.test"
                ) as client:
                    return await scenario(app, Browser(client))

        return asyncio.run(wrapped())

    return run_scenario


def _address() -> str:
    return f"student-{secrets.token_hex(4)}@example.com"


def _phone() -> str:
    return f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"


def _google_account(
    email: str, *, subject: str | None = None, verified: bool = True
) -> GoogleAccount:
    return GoogleAccount(
        subject=subject or str(10**20 + secrets.randbelow(10**20)),
        email=email,
        email_verified=verified,
        hosted_domain=None,
    )


async def _ask_for_code(browser: Browser, email: str) -> httpx.Response:
    return await browser.request(
        "POST",
        "/v1/auth/email/request",
        csrf=True,
        json={"email": email, "humanCheckToken": "XXXX.DUMMY.TOKEN.XXXX"},
    )


async def _verify(
    browser: Browser, challenge_id: str, code: str, *, consent: bool = True
) -> httpx.Response:
    body: dict[str, object] = {"challengeId": challenge_id, "code": code}
    if consent:
        body["consent"] = CONSENT
    return await browser.request("POST", "/v1/auth/otp/verify", csrf=True, json=body)


async def _sign_in_by_email(browser: Browser, mail: RecordingMail, email: str) -> httpx.Response:
    asked = await _ask_for_code(browser, email)
    assert asked.status_code == 202, asked.text
    return await _verify(browser, asked.json()["challengeId"], mail.sent[-1][1])


async def _user_with_email(app: FastAPI, email: str) -> User | None:
    async with app.state.sessionmaker() as db, db.begin():
        return await UserRepository(db).by_email(email)


async def _google(
    browser: Browser, google: FakeGoogle, account: GoogleAccount, **params: Any
) -> httpx.Response:
    """Sign in with Google from the start: leave for Google, pick ``account``, come back."""
    started = await browser.request("GET", "/v1/auth/google", params=params)
    assert started.status_code == 303, started.text
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    code = google.choose(account)
    return await browser.request("GET", CALLBACK, params={"code": code, "state": state})


def _went_to(response: httpx.Response) -> tuple[str, dict[str, list[str]]]:
    assert response.status_code == 303, response.text
    where = urlsplit(response.headers["location"])
    return f"{where.scheme}://{where.netloc}{where.path}", parse_qs(where.query)


async def _me(browser: Browser) -> dict[str, Any]:
    response = await browser.request("GET", "/v1/me")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# Email codes.


def test_an_email_code_makes_an_account_with_that_address(
    run: Callable[..., Any], mail: RecordingMail
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()

        asked = await _ask_for_code(browser, f"  {email.upper()} ")

        assert asked.status_code == 202
        assert asked.json()["developmentCode"] is None
        assert mail.sent == [(email, mail.sent[-1][1])]
        signed_in = await _verify(browser, asked.json()["challengeId"], mail.sent[-1][1])
        assert signed_in.status_code == 200, signed_in.text
        body = signed_in.json()
        assert body["newUser"] is True
        assert (body["user"]["email"], body["user"]["phone"]) == (email, None)
        assert (await _me(browser))["id"] == body["user"]["id"]
        async with app.state.sessionmaker() as db:
            challenge = await db.scalar(select(OtpChallenge).where(OtpChallenge.email == email))
            assert challenge is not None
            assert challenge.phone_e164 is None
            # Ten minutes for mail, which can be slow to arrive.
            assert challenge.expires_at - challenge.requested_at == EMAIL_CODE_TTL

    run(scenario)


def test_an_email_code_signs_in_to_the_account_with_that_address(
    run: Callable[..., Any], mail: RecordingMail, clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        first = await _sign_in_by_email(browser, mail, email)
        await browser.request("POST", "/v1/auth/logout", csrf=True)
        clock.advance(RESEND_COOLDOWN)

        asked = await _ask_for_code(browser, email)
        again = await _verify(browser, asked.json()["challengeId"], mail.sent[-1][1], consent=False)

        assert again.status_code == 200, again.text
        assert again.json()["newUser"] is False
        assert again.json()["user"]["id"] == first.json()["user"]["id"]

    run(scenario)


def test_a_first_email_sign_in_needs_consent_and_the_code_waits_for_it(
    run: Callable[..., Any], mail: RecordingMail
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        asked = await _ask_for_code(browser, email)
        challenge_id, code = asked.json()["challengeId"], mail.sent[-1][1]

        refused = await _verify(browser, challenge_id, code, consent=False)

        assert (refused.status_code, refused.json()["code"]) == (400, "CONSENT_REQUIRED")
        assert await _user_with_email(app, email) is None
        assert (await _verify(browser, challenge_id, code)).status_code == 200

    run(scenario)


def test_an_owner_ops_gave_an_address_signs_in_with_it(
    run: Callable[..., Any], mail: RecordingMail
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        phone, email = _phone(), _address()
        async with app.state.sessionmaker() as db, db.begin():
            await Accounts(db).ensure(phone, role=Role.OWNER, name="Fictional Owner", email=email)

        signed_in = await _sign_in_by_email(browser, mail, email.upper())

        assert signed_in.status_code == 200, signed_in.text
        user = signed_in.json()["user"]
        assert (user["phone"], user["email"], user["roles"]) == (phone, email, ["owner"])
        # Their first sign-in, with consent; the account itself was made for them by ops.
        assert signed_in.json()["newUser"] is False

    run(scenario)


def test_an_address_goes_on_one_account_and_an_account_keeps_its_address(
    run: Callable[..., Any],
) -> None:
    async def scenario(app: FastAPI, _browser: Browser) -> None:
        email = _address()
        async with app.state.sessionmaker() as db, db.begin():
            accounts = Accounts(db)
            first = await accounts.ensure(_phone(), role=Role.OWNER, email=email)
            # The same address again changes nothing.
            assert await accounts.add_email(first.id, email) is False
            second = await accounts.ensure(_phone(), role=Role.OWNER)
            with pytest.raises(EmailTakenError):
                await accounts.add_email(second.id, email)
            with pytest.raises(EmailTakenError):
                await accounts.add_email(first.id, _address())
            assert await accounts.add_email(second.id, _address()) is True

    run(scenario)


def test_codes_to_one_address_wait_between_sends(
    run: Callable[..., Any], mail: RecordingMail
) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        email = _address()
        assert (await _ask_for_code(browser, email)).status_code == 202

        again = await _ask_for_code(browser, email)

        assert (again.status_code, again.json()["code"]) == (429, "OTP_RESEND_TOO_SOON")
        assert len(mail.sent) == 1

    run(scenario)


def test_an_address_that_isnt_one_is_refused(run: Callable[..., Any], mail: RecordingMail) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        for wrong in ("not-an-address", "a@b", "two@@example.com", "a b@example.com"):
            response = await _ask_for_code(browser, wrong)
            assert response.status_code == 422, wrong
            assert response.json()["errors"][0]["code"] == "email_invalid"
        assert mail.sent == []

    run(scenario)


def test_a_test_site_shows_email_codes_until_mail_is_set_up(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        asked = await _ask_for_code(browser, _address())

        assert asked.status_code == 202
        code = asked.json()["developmentCode"]
        assert code is not None
        assert (await _verify(browser, asked.json()["challengeId"], code)).status_code == 200

    run(scenario, fakes=False, mail_sender="unavailable", otp_sender="screen")


def test_without_mail_or_a_test_site_email_sign_in_is_off(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        methods = await browser.request("GET", "/v1/auth/methods")
        asked = await _ask_for_code(browser, email)

        assert methods.json() == {"phone": False, "email": False, "google": False}
        assert (asked.status_code, asked.json()["code"]) == (503, "SERVICE_UNAVAILABLE")
        async with app.state.sessionmaker() as db:
            left = await db.scalars(select(OtpChallenge).where(OtpChallenge.email == email))
            assert left.all() == []

    run(scenario, fakes=False, mail_sender="unavailable", otp_sender="unavailable")


def test_phone_sign_in_can_be_switched_off_while_email_works(
    run: Callable[..., Any], mail: RecordingMail
) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        methods = await browser.request("GET", "/v1/auth/methods")
        by_phone = await browser.request(
            "POST",
            "/v1/auth/otp/request",
            csrf=True,
            json={"phone": _phone(), "humanCheckToken": "XXXX.DUMMY.TOKEN.XXXX"},
        )

        assert methods.json() == {"phone": False, "email": True, "google": True}
        assert (by_phone.status_code, by_phone.json()["code"]) == (503, "SERVICE_UNAVAILABLE")
        assert (await _sign_in_by_email(browser, mail, _address())).status_code == 200

    run(scenario, phone_sign_in=False)


# Google.


def test_google_makes_an_account_with_its_address_and_goes_back(
    run: Callable[..., Any], google: FakeGoogle
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()

        came_back = await _google(
            browser,
            google,
            _google_account(email.upper()),
            notice=NOTICE_VERSION,
            purpose=["account"],
            next="/pg/a-fictional-pg?moveIn=2027-08",
        )

        assert google.any_account is True
        assert came_back.headers["location"] == f"{SITE}/pg/a-fictional-pg?moveIn=2027-08"
        assert GOOGLE_LOGIN_COOKIE not in browser.cookies
        me = await _me(browser)
        assert (me["email"], me["phone"], me["roles"]) == (email, None, [])
        async with app.state.sessionmaker() as db:
            linked = await db.scalar(
                select(UserIdentity)
                .where(UserIdentity.provider == IdentityProvider.GOOGLE)
                .where(UserIdentity.email == email)
            )
            assert linked is not None
            audited = await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "user.google_linked")
            )
            assert audited

    run(scenario)


def test_a_first_google_sign_in_without_consent_comes_back_for_it(
    run: Callable[..., Any], google: FakeGoogle
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()

        came_back = await _google(browser, google, _google_account(email), next="/visits")

        assert _went_to(came_back) == (
            f"{SITE}/sign-in",
            {"error": ["CONSENT_REQUIRED"], "next": ["/visits"]},
        )
        assert SESSION_COOKIE not in browser.cookies
        assert await _user_with_email(app, email) is None

    run(scenario)


def test_google_signs_in_to_the_account_with_its_address_and_then_by_its_id(
    run: Callable[..., Any], google: FakeGoogle, mail: RecordingMail
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        first = await _sign_in_by_email(browser, mail, email)
        await browser.request("POST", "/v1/auth/logout", csrf=True)
        account = _google_account(email)

        came_back = await _google(browser, google, account)

        assert came_back.headers["location"] == f"{SITE}/account"
        assert (await _me(browser))["id"] == first.json()["user"]["id"]
        # The Google account's id finds the account from now on, whatever its address becomes.
        await browser.request("POST", "/v1/auth/logout", csrf=True)
        renamed = GoogleAccount(
            subject=account.subject,
            email=_address(),
            email_verified=True,
            hosted_domain=None,
        )
        await _google(browser, google, renamed)
        assert (await _me(browser))["id"] == first.json()["user"]["id"]

    run(scenario)


@pytest.mark.parametrize("problem", ["unverified", "linked_elsewhere"])
def test_a_google_account_that_cant_prove_the_address_is_refused(
    run: Callable[..., Any], google: FakeGoogle, problem: str
) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        email = _address()
        if problem == "linked_elsewhere":
            # The address's account signs in with one Google account; another now has the address.
            await _google(
                browser, google, _google_account(email), notice=NOTICE_VERSION, purpose="account"
            )
            await browser.request("POST", "/v1/auth/logout", csrf=True)
        account = _google_account(email, verified=problem != "unverified")

        came_back = await _google(browser, google, account, notice=NOTICE_VERSION)

        assert _went_to(came_back) == (f"{SITE}/sign-in", {"error": ["GOOGLE_ACCOUNT_NOT_USABLE"]})
        assert SESSION_COOKIE not in browser.cookies

    run(scenario)


def test_a_stale_or_tampered_google_sign_in_starts_again(
    run: Callable[..., Any], google: FakeGoogle, clock: FrozenClock
) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        await browser.request("GET", "/v1/auth/google", params={"next": "/search"})
        code = google.choose(_google_account(_address()))

        tampered = await browser.request("GET", CALLBACK, params={"code": code, "state": "x" * 43})
        assert _went_to(tampered) == (
            f"{SITE}/sign-in",
            {"error": ["GOOGLE_SIGN_IN_EXPIRED"], "next": ["/search"]},
        )

        restarted = await browser.request("GET", "/v1/auth/google")
        state = parse_qs(urlsplit(restarted.headers["location"]).query)["state"][0]
        clock.advance(LOGIN_TTL * 2)
        stale = await browser.request("GET", CALLBACK, params={"code": code, "state": state})
        assert _went_to(stale)[1]["error"] == ["GOOGLE_SIGN_IN_EXPIRED"]

    run(scenario)


def test_cancelling_at_google_comes_back_saying_so(run: Callable[..., Any]) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        started = await browser.request("GET", "/v1/auth/google")
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]

        cancelled = await browser.request(
            "GET", CALLBACK, params={"error": "access_denied", "state": state}
        )

        assert _went_to(cancelled)[1] == {"error": ["GOOGLE_SIGN_IN_CANCELLED"]}

    run(scenario)


@pytest.mark.parametrize("elsewhere", ["//evil.example/x", "https://evil.example", "/\\evil"])
def test_google_goes_back_only_to_a_page_of_the_site(
    run: Callable[..., Any], google: FakeGoogle, elsewhere: str
) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        came_back = await _google(
            browser,
            google,
            _google_account(_address()),
            notice=NOTICE_VERSION,
            purpose="account",
            next=elsewhere,
        )

        assert came_back.headers["location"] == f"{SITE}/account"

    run(scenario)


def test_google_gives_staff_an_ordinary_session_here(
    run: Callable[..., Any], google: FakeGoogle
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        async with app.state.sessionmaker() as db, db.begin():
            user = await UserRepository(db).add(phone_e164=_phone(), roles=(Role.OPS,))
            user.email = email

        await _google(
            browser, google, _google_account(email), notice=NOTICE_VERSION, purpose="account"
        )

        assert (await _me(browser))["roles"] == []

    run(scenario)


def test_google_for_everyone_can_wait_for_the_oauth_client(run: Callable[..., Any]) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        methods = await browser.request("GET", "/v1/auth/methods")
        started = await browser.request("GET", "/v1/auth/google")

        assert methods.json()["google"] is False
        assert _went_to(started) == (f"{SITE}/sign-in", {"error": ["SERVICE_UNAVAILABLE"]})

    run(scenario, google_sign_in_for_everyone=False)


def test_a_staff_sign_in_in_the_same_browser_still_finishes_as_staff(
    run: Callable[..., Any], google: FakeGoogle
) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        # A people sign-in left unfinished, then a staff one: the callback finishes the staff one.
        await browser.request("GET", "/v1/auth/google")
        staff = await browser.request("GET", "/v1/auth/staff/google")
        state = parse_qs(urlsplit(staff.headers["location"]).query)["state"][0]
        assert STAFF_LOGIN_COOKIE in browser.cookies
        code = google.choose(_google_account(_address()))

        came_back = await browser.request("GET", CALLBACK, params={"code": code, "state": state})

        # Not a staff member: refused by the staff flow, on the staff sign-in page.
        assert _went_to(came_back) == (
            f"{SITE}/staff/sign-in",
            {"error": ["STAFF_ACCOUNT_NOT_ALLOWED"]},
        )

    run(scenario, staff_google_domains=frozenset({"example.in"}))
