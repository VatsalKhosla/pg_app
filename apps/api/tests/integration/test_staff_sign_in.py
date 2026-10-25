"""Staff sign-in end to end (step 1.3): Google, the authenticator fallback and staff-only routes.

The app runs against PostgreSQL and Valkey with a frozen clock. A fake Google stands in for the
real one: it answers a code with the account the test picked, and checks the PKCE verifier and the
nonce the way Google and the real adapter do. Staff are made the way an operator makes them, with
StaffAdmin (python -m app.manage).
"""

import asyncio
import base64
import hashlib
import io
import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from app.core.clock import FrozenClock
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, STAFF_LOGIN_COOKIE
from app.core.csrf import issue_csrf_token
from app.main import create_app
from app.manage import main as manage
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.domain.staff import GoogleAccount
from app.modules.identity.domain.totp import code_at, time_step
from app.modules.identity.errors import StaffSignInExpiredError
from app.modules.identity.models import User, UserIdentity
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import SessionService, StaffAdmin
from tests.conftest import TEST_SECRET_KEY

pytestmark = pytest.mark.integration

type SettingsFactory = Callable[..., Settings]
type Scenario = Callable[[FastAPI, Browser], Awaitable[Any]]

START = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)
SITE = "https://www.example.in"
DOMAIN = "example.in"
STAFF_HOME = f"{SITE}/staff"


def _refused_with(code: str) -> str:
    return f"{SITE}/staff/sign-in?error={code}"


class FakeGoogle:
    """Google, as far as the API can tell. ``choose`` plays the person picking an account at
    Google, for the sign-in the API started last."""

    def __init__(self) -> None:
        self._started: tuple[str, str] | None = None
        self._codes: dict[str, tuple[GoogleAccount, str, str]] = {}

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        self._started = (nonce, code_challenge)
        return f"https://accounts.google.test/o/oauth2/v2/auth?state={state}"

    def choose(self, account: GoogleAccount) -> str:
        assert self._started is not None, "no sign-in was started"
        code = secrets.token_urlsafe(16)
        self._codes[code] = (account, *self._started)
        return code

    async def finish(self, code: str, *, code_verifier: str, nonce: str) -> GoogleAccount:
        # A code works once; the verifier must hash to the challenge, and the nonce must match.
        issued = self._codes.pop(code, None)
        if issued is None:
            raise StaffSignInExpiredError
        account, issued_nonce, challenge = issued
        digest = hashlib.sha256(code_verifier.encode()).digest()
        if base64.urlsafe_b64encode(digest).decode().rstrip("=") != challenge:
            raise StaffSignInExpiredError
        if nonce != issued_nonce:
            raise StaffSignInExpiredError
        return account


class Browser:
    """One browser: its own cookies, kept by hand, so a test says exactly what is sent."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self.cookies: dict[str, str] = {}

    async def request(
        self, method: str, path: str, *, csrf: bool = False, **kwargs: Any
    ) -> httpx.Response:
        headers: dict[str, str] = dict(kwargs.pop("headers", {}))
        if csrf:
            token = issue_csrf_token(TEST_SECRET_KEY.encode(), self.cookies.get(SESSION_COOKIE))
            self.cookies[CSRF_COOKIE] = token
            headers[CSRF_HEADER] = token
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        self._client.cookies.clear()
        response = await self._client.request(method, path, headers=headers, **kwargs)
        self._client.cookies.clear()
        for header in response.headers.get_list("set-cookie"):
            name, _, rest = header.partition("=")
            value = rest.split(";", 1)[0]
            if "max-age=0" in header.lower():
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = value
        return response

    def other(self) -> Browser:
        """Another browser, on the same network."""
        return Browser(self._client)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(START)


@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture
def run(
    make_settings: SettingsFactory,
    database_url: str,
    valkey_url: str,
    clock: FrozenClock,
    google: FakeGoogle,
) -> Callable[..., Any]:
    """Run a scenario against the app (lifespan open, the fake Google in place unless
    ``with_google`` is False) from a client address of its own, so per-IP limits stay apart."""

    def run_scenario(scenario: Scenario, *, with_google: bool = True, **settings: object) -> Any:
        values: dict[str, object] = {
            "site_url": SITE,
            "staff_google_domains": frozenset({DOMAIN}),
        }
        values.update(settings)
        app = create_app(
            make_settings(database_url=database_url, redis_url=valkey_url, **values),
            clock=clock,
        )
        address = f"10.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}"

        async def wrapped() -> Any:
            async with app.router.lifespan_context(app):
                if with_google:
                    app.state.google_sign_in = google
                transport = httpx.ASGITransport(app=app, client=(address, 50_000))
                async with httpx.AsyncClient(
                    transport=transport, base_url="https://api.test"
                ) as client:
                    return await scenario(app, Browser(client))

        return asyncio.run(wrapped())

    return run_scenario


def _new_phone() -> str:
    return f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"


def _address(domain: str = DOMAIN) -> str:
    return f"staff-{secrets.token_hex(4)}@{domain}"


def _google_account(
    email: str, *, hosted_domain: str | None = DOMAIN, subject: str | None = None
) -> GoogleAccount:
    return GoogleAccount(
        subject=subject or str(10**20 + secrets.randbelow(10**20)),
        email=email,
        email_verified=True,
        hosted_domain=hosted_domain,
    )


def _admin(app: FastAPI, db: AsyncSession) -> StaffAdmin:
    return StaffAdmin(db, app.state.clock, secret=TEST_SECRET_KEY.encode())


async def _make_staff(app: FastAPI, *roles: Role, email: str | None = None) -> str:
    """A staff member, made the way an operator does it. Returns their phone number."""
    phone = _new_phone()
    async with app.state.sessionmaker() as db:
        await _admin(app, db).add(phone, frozenset(roles or (Role.OPS,)), email=email, name=None)
    return phone


async def _make_user(app: FastAPI, *, email: str | None = None) -> str:
    """Someone who isn't staff (a student). Returns their phone number."""
    phone = _new_phone()
    async with app.state.sessionmaker() as db, db.begin():
        user = await UserRepository(db).add(phone_e164=phone, roles=(Role.STUDENT,))
        user.email = email
    return phone


async def _user(app: FastAPI, phone: str) -> User:
    async with app.state.sessionmaker() as db, db.begin():
        user = await UserRepository(db).by_phone(phone)
        assert user is not None
        return user


async def _session(app: FastAPI, phone: str, *, kind: SessionKind = SessionKind.USER) -> str:
    """A session token for the account, as a phone sign-in (or a staff sign-in) gives it."""
    user = await _user(app, phone)
    async with app.state.sessionmaker() as db:
        issued = await SessionService(db, app.state.clock).start(
            user.id, kind=kind, ip_address=None, user_agent=None
        )
    return issued.token


async def _enrol(app: FastAPI, phone: str, *, confirm: bool = True) -> bytes:
    """Set up an authenticator app for the staff member; returns the app's secret."""
    async with app.state.sessionmaker() as db:
        admin = _admin(app, db)
        enrolment = await admin.enrol_authenticator(phone)
        secret = base64.b32decode(enrolment.secret + "=" * (-len(enrolment.secret) % 8))
        if confirm:
            code = code_at(secret, time_step(app.state.clock.now()))
            assert await admin.confirm_authenticator(phone, code)
    return secret


def _code_now(app: FastAPI, secret: bytes) -> str:
    return code_at(secret, time_step(app.state.clock.now()))


def _wrong_code(app: FastAPI, secret: bytes) -> str:
    """A code the app isn't showing now, nor a step either side."""
    step = time_step(app.state.clock.now())
    valid = {code_at(secret, step + offset) for offset in (-1, 0, 1)}
    return next(f"{n:06d}" for n in range(10**6) if f"{n:06d}" not in valid)


async def _start(browser: Browser) -> str:
    """Start a Google sign-in; returns the state Google would send back."""
    response = await browser.request("GET", "/v1/auth/staff/google")
    assert response.status_code == 303
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


async def _come_back(browser: Browser, **params: str) -> httpx.Response:
    return await browser.request("GET", "/v1/auth/staff/google/callback", params=params)


async def _google_sign_in(
    browser: Browser, google: FakeGoogle, account: GoogleAccount
) -> httpx.Response:
    state = await _start(browser)
    return await _come_back(browser, code=google.choose(account), state=state)


async def _audit_actions(app: FastAPI, phone: str) -> list[str]:
    user = await _user(app, phone)
    async with app.state.sessionmaker() as db:
        rows = await db.scalars(
            select(AuditLog.action)
            .where(AuditLog.entity_type == "user", AuditLog.entity_id == str(user.public_id))
            .order_by(AuditLog.id)
        )
        return list(rows)


def test_staff_of_an_allowed_workspace_sign_in_with_google_for_12_hours(
    run: Callable[..., Any], google: FakeGoogle, clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        phone = await _make_staff(app, Role.OPS, email=email)

        response = await _google_sign_in(browser, google, _google_account(email))

        assert response.status_code == 303
        assert response.headers["location"] == STAFF_HOME
        session_cookie = next(
            header
            for header in response.headers.get_list("set-cookie")
            if header.startswith(f"{SESSION_COOKIE}=")
        )
        assert "Max-Age=43200" in session_cookie
        assert "HttpOnly" in session_cookie
        assert STAFF_LOGIN_COOKIE not in browser.cookies
        assert CSRF_COOKIE in browser.cookies
        assert (await browser.request("GET", "/v1/me")).json()["roles"] == ["ops"]
        assert await _audit_actions(app, phone) == [
            "staff.roles_granted",
            "staff.google_linked",
            "staff.sign_in",
        ]

        clock.advance(timedelta(hours=12))
        assert (await browser.request("GET", "/v1/me")).status_code == 401

    run(scenario)


def test_a_google_account_that_isnt_allowed_is_refused_even_for_staff(
    run: Callable[..., Any], google: FakeGoogle
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        elsewhere = _address("other.in")
        await _make_staff(app, Role.OPS, email=elsewhere)
        lookalike = _address()
        await _make_staff(app, Role.OPS, email=lookalike)

        refused = [
            # A Workspace that isn't allowed.
            await _google_sign_in(
                browser, google, _google_account(elsewhere, hosted_domain="other.in")
            ),
            # A personal account whose address merely ends in the company's domain.
            await _google_sign_in(browser, google, _google_account(lookalike, hosted_domain=None)),
            # An address Google hasn't verified.
            await _google_sign_in(
                browser,
                google,
                GoogleAccount(
                    subject="1", email=lookalike, email_verified=False, hosted_domain=DOMAIN
                ),
            ),
        ]

        assert [response.headers["location"] for response in refused] == [
            _refused_with("STAFF_ACCOUNT_NOT_ALLOWED")
        ] * 3
        assert SESSION_COOKIE not in browser.cookies
        assert STAFF_LOGIN_COOKIE not in browser.cookies

    run(scenario)


@pytest.mark.parametrize("who", ["no-account", "not-staff", "suspended"])
def test_an_allowed_google_account_must_belong_to_active_staff(
    run: Callable[..., Any], google: FakeGoogle, who: str
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        if who == "not-staff":
            await _make_user(app, email=email)
        elif who == "suspended":
            phone = await _make_staff(app, Role.ADMIN, email=email)
            async with app.state.sessionmaker() as db, db.begin():
                await db.execute(
                    update(User).where(User.phone_e164 == phone).values(status="suspended")
                )
        account = _google_account(email)

        response = await _google_sign_in(browser, google, account)

        assert response.headers["location"] == _refused_with("STAFF_ACCOUNT_NOT_ALLOWED")
        async with app.state.sessionmaker() as db:
            linked = await db.scalar(
                select(func.count())
                .select_from(UserIdentity)
                .where(UserIdentity.subject == account.subject)
            )
        assert linked == 0

    run(scenario)


def test_an_allowed_address_signs_in_without_a_workspace(
    run: Callable[..., Any], google: FakeGoogle
) -> None:
    address = _address("gmail.com")

    async def scenario(app: FastAPI, browser: Browser) -> None:
        await _make_staff(app, Role.ADMIN, email=address)

        response = await _google_sign_in(
            browser, google, _google_account(address.upper(), hosted_domain=None)
        )

        assert response.headers["location"] == STAFF_HOME
        assert (await browser.request("GET", "/v1/me")).json()["roles"] == ["admin"]

    run(scenario, staff_google_emails=frozenset({address}))


def test_the_google_account_is_linked_once_and_then_known_by_its_id(
    run: Callable[..., Any], google: FakeGoogle
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        phone = await _make_staff(app, Role.OPS, email=email)
        subject = str(10**20 + secrets.randbelow(10**20))

        first = await _google_sign_in(browser, google, _google_account(email, subject=subject))
        # The account's address changed at Google: it is still the same account.
        renamed = await _google_sign_in(
            browser.other(), google, _google_account(_address(), subject=subject)
        )
        # A different Google account that now has the old address doesn't get in...
        replacement = _google_account(email)
        taken_over = await _google_sign_in(browser.other(), google, replacement)
        # ...until an operator unlinks the old one (python -m app.manage staff remove-google).
        async with app.state.sessionmaker() as db:
            assert await _admin(app, db).remove_google(phone)
        relinked = await _google_sign_in(browser.other(), google, replacement)

        assert first.headers["location"] == STAFF_HOME
        assert renamed.headers["location"] == STAFF_HOME
        assert taken_over.headers["location"] == _refused_with("STAFF_ACCOUNT_NOT_ALLOWED")
        assert relinked.headers["location"] == STAFF_HOME
        assert (await _audit_actions(app, phone))[-3:] == [
            "staff.google_unlinked",
            "staff.google_linked",
            "staff.sign_in",
        ]

    run(scenario)


def test_a_sign_in_is_finished_only_by_its_browser_within_ten_minutes(
    run: Callable[..., Any], google: FakeGoogle, clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        await _make_staff(app, Role.OPS, email=email)
        account = _google_account(email)
        expired = _refused_with("STAFF_SIGN_IN_EXPIRED")

        # Finished in a browser that didn't start it.
        state = await _start(browser)
        elsewhere = await _come_back(browser.other(), code=google.choose(account), state=state)
        # With the state of an earlier sign-in from the same browser.
        earlier_state = await _start(browser)
        await _start(browser)
        stale = await _come_back(browser, code=google.choose(account), state=earlier_state)
        # After ten minutes.
        state = await _start(browser)
        clock.advance(timedelta(minutes=10, seconds=1))
        late = await _come_back(browser, code=google.choose(account), state=state)
        # With a login cookie that was tampered with.
        state = await _start(browser)
        login = browser.cookies[STAFF_LOGIN_COOKIE]
        browser.cookies[STAFF_LOGIN_COOKIE] = ("B" if login[0] == "A" else "A") + login[1:]
        tampered = await _come_back(browser, code=google.choose(account), state=state)
        # The same code twice.
        state = await _start(browser)
        login = browser.cookies[STAFF_LOGIN_COOKIE]
        code = google.choose(account)
        signed_in = await _come_back(browser, code=code, state=state)
        browser.cookies[STAFF_LOGIN_COOKIE] = login
        replayed = await _come_back(browser, code=code, state=state)

        assert [
            response.headers["location"] for response in (elsewhere, stale, late, tampered)
        ] == [expired] * 4
        assert signed_in.headers["location"] == STAFF_HOME
        assert replayed.headers["location"] == expired

    run(scenario)


def test_cancelling_at_google_comes_back_as_cancelled(run: Callable[..., Any]) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        state = await _start(browser)

        response = await _come_back(browser, error="access_denied", state=state)

        assert response.headers["location"] == _refused_with("STAFF_SIGN_IN_CANCELLED")
        assert STAFF_LOGIN_COOKIE not in browser.cookies

    run(scenario)


def test_google_sign_in_answers_unavailable_until_it_is_set_up(run: Callable[..., Any]) -> None:
    async def scenario(_app: FastAPI, browser: Browser) -> None:
        response = await browser.request("GET", "/v1/auth/staff/google")

        assert response.status_code == 303
        assert response.headers["location"] == _refused_with("SERVICE_UNAVAILABLE")
        assert STAFF_LOGIN_COOKIE not in browser.cookies

    run(scenario, with_google=False)


def test_staff_sessions_stop_working_with_the_last_staff_role(
    run: Callable[..., Any], google: FakeGoogle
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        phone = await _make_staff(app, Role.OPS, Role.ADMIN, email=email)
        await _google_sign_in(browser, google, _google_account(email))
        assert (await browser.request("GET", "/v1/me")).json()["roles"] == ["admin", "ops"]

        async with app.state.sessionmaker() as db:
            await _admin(app, db).remove(phone, frozenset({Role.ADMIN}))
        assert (await browser.request("GET", "/v1/me")).json()["roles"] == ["ops"]

        async with app.state.sessionmaker() as db:
            await _admin(app, db).remove(phone, None)
        assert (await browser.request("GET", "/v1/me")).status_code == 401

    run(scenario)


def test_staff_step_up_from_a_phone_sign_in_with_an_authenticator_code(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        phone = await _make_staff(app, Role.OPS)
        secret = await _enrol(app, phone)
        phone_session = await _session(app, phone)
        browser.cookies[SESSION_COOKIE] = phone_session
        assert (await browser.request("GET", "/v1/me")).json()["roles"] == []

        # The code that confirmed the app was used up; the app shows the next one 30 s later.
        clock.advance(timedelta(seconds=30))
        response = await browser.request(
            "POST", "/v1/auth/staff/totp", csrf=True, json={"code": _code_now(app, secret)}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["user"]["roles"] == ["ops"]
        assert body["csrfToken"] == browser.cookies[CSRF_COOKIE]
        assert browser.cookies[SESSION_COOKIE] != phone_session
        assert (await browser.request("GET", "/v1/me")).json()["roles"] == ["ops"]
        # The phone session it replaced has ended.
        old = await browser.other().request(
            "GET", "/v1/me", headers={"Cookie": f"{SESSION_COOKIE}={phone_session}"}
        )
        assert old.status_code == 401
        assert (await _audit_actions(app, phone))[-1] == "staff.sign_in"

    run(scenario)


def test_a_wrong_or_used_authenticator_code_is_refused(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        phone = await _make_staff(app, Role.OPS)
        secret = await _enrol(app, phone)
        clock.advance(timedelta(seconds=30))
        code = _code_now(app, secret)
        wrong = _wrong_code(app, secret)

        async def step_up(code: str) -> httpx.Response:
            phone_browser = browser.other()
            phone_browser.cookies[SESSION_COOKIE] = await _session(app, phone)
            return await phone_browser.request(
                "POST", "/v1/auth/staff/totp", csrf=True, json={"code": code}
            )

        refused = await step_up(wrong)
        accepted = await step_up(code)
        replayed = await step_up(code)

        assert (refused.status_code, refused.json()["code"]) == (400, "TOTP_INVALID")
        assert accepted.status_code == 200
        assert (replayed.status_code, replayed.json()["code"]) == (400, "TOTP_INVALID")

    run(scenario)


def test_authenticator_codes_are_limited_to_five_tries_per_15_minutes(
    run: Callable[..., Any], clock: FrozenClock
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        phone = await _make_staff(app, Role.OPS)
        secret = await _enrol(app, phone)
        clock.advance(timedelta(seconds=30))
        browser.cookies[SESSION_COOKIE] = await _session(app, phone)
        right = _code_now(app, secret)
        wrong = _wrong_code(app, secret)

        async def step_up(code: str) -> httpx.Response:
            return await browser.request(
                "POST", "/v1/auth/staff/totp", csrf=True, json={"code": code}
            )

        statuses = [(await step_up(wrong)).status_code for _ in range(5)]
        limited = await step_up(right)

        assert statuses == [400] * 5
        assert (limited.status_code, limited.json()["code"]) == (429, "RATE_LIMITED")

    run(scenario)


@pytest.mark.parametrize("who", ["not-staff", "no-authenticator", "unconfirmed-authenticator"])
def test_only_staff_with_a_confirmed_authenticator_can_step_up(
    run: Callable[..., Any], who: str
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        if who == "not-staff":
            phone = await _make_user(app)
            code = "123456"
        else:
            phone = await _make_staff(app, Role.OPS)
            code = "123456"
            if who == "unconfirmed-authenticator":
                code = _code_now(app, await _enrol(app, phone, confirm=False))
        browser.cookies[SESSION_COOKIE] = await _session(app, phone)

        response = await browser.request(
            "POST", "/v1/auth/staff/totp", csrf=True, json={"code": code}
        )

        assert (response.status_code, response.json()["code"]) == (
            403,
            "STAFF_ACCOUNT_NOT_ALLOWED",
        )

    run(scenario)


def test_the_staff_list_is_for_admins_in_a_staff_session(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        admin = await _make_staff(app, Role.ADMIN)
        ops = await _make_staff(app, Role.OPS)

        async def list_as(token: str | None) -> httpx.Response:
            headers = {} if token is None else {"Cookie": f"{SESSION_COOKIE}={token}"}
            return await browser.other().request("GET", "/v1/admin/staff", headers=headers)

        anonymous = await list_as(None)
        admins_phone_session = await list_as(await _session(app, admin))
        ops_staff_session = await list_as(await _session(app, ops, kind=SessionKind.STAFF))
        admin_staff_session = await list_as(await _session(app, admin, kind=SessionKind.STAFF))

        assert (anonymous.status_code, anonymous.json()["code"]) == (401, "UNAUTHENTICATED")
        assert (admins_phone_session.status_code, admins_phone_session.json()["code"]) == (
            403,
            "FORBIDDEN",
        )
        assert (ops_staff_session.status_code, ops_staff_session.json()["code"]) == (
            403,
            "FORBIDDEN",
        )
        assert admin_staff_session.status_code == 200

    run(scenario)


def test_the_staff_list_pages_by_cursor_in_a_fixed_number_of_queries(
    run: Callable[..., Any], google: FakeGoogle
) -> None:
    async def scenario(app: FastAPI, browser: Browser) -> None:
        email = _address()
        linked = await _make_staff(app, Role.ADMIN, email=email)
        await _google_sign_in(browser.other(), google, _google_account(email))
        await _enrol(app, linked)
        made = {linked, *[await _make_staff(app, Role.FIELD_AGENT) for _ in range(5)]}
        browser.cookies[SESSION_COOKIE] = await _session(app, linked, kind=SessionKind.STAFF)

        statements = 0

        def count(*_: object) -> None:
            nonlocal statements
            statements += 1

        event.listen(app.state.engine.sync_engine, "before_cursor_execute", count)
        seen: list[dict[str, Any]] = []
        cursor: str | None = None
        queries_per_page = set()
        while True:
            statements = 0
            params = {"limit": "2"} | ({} if cursor is None else {"cursor": cursor})
            page = (await browser.request("GET", "/v1/admin/staff", params=params)).json()
            queries_per_page.add(statements)
            assert len(page["items"]) <= 2
            seen.extend(page["items"])
            cursor = page["nextCursor"]
            if cursor is None:
                break
        statements = 0
        await browser.request("GET", "/v1/admin/staff", params={"limit": "50"})
        queries_per_page.add(statements)
        event.remove(app.state.engine.sync_engine, "before_cursor_execute", count)

        ids = [item["id"] for item in seen]
        assert ids == sorted(ids)
        assert len(ids) == len(set(ids))
        mine = {item["phone"]: item for item in seen if item["phone"] in made}
        assert set(mine) == made
        assert mine[linked]["googleAccount"] == email
        assert mine[linked]["authenticator"] is True
        assert mine[linked]["roles"] == ["admin"]
        # However many staff a page holds, the same number of queries.
        assert len(queries_per_page) == 1

    run(scenario)


def test_operators_manage_staff_from_the_command_line(
    make_settings: SettingsFactory, database_url: str, clock: FrozenClock
) -> None:
    settings = make_settings(database_url=database_url)
    phone = _new_phone()
    email = _address()
    out = io.StringIO()

    def cli(*argv: str, read_code: Callable[[], str] | None = None) -> int:
        return manage(list(argv), settings=settings, clock=clock, out=out, read_code=read_code)

    def code_from_the_printed_key() -> str:
        key = re.search(r"^    ((?:[A-Z2-7]{4} ?)+)$", out.getvalue(), re.MULTILINE)
        assert key is not None
        secret_text = key.group(1).replace(" ", "")
        secret = base64.b32decode(secret_text + "=" * (-len(secret_text) % 8))
        return code_at(secret, time_step(clock.now()))

    assert cli("staff", "add", phone, "--role", "ops", "--email", email, "--name", "Asha") == 0
    assert cli("staff", "enrol-authenticator", phone, read_code=code_from_the_printed_key) == 0
    assert cli("staff", "list") == 0
    assert cli("staff", "remove", phone) == 0
    assert cli("staff", "add", "not a phone", "--role", "ops") == 1

    output = out.getvalue()
    assert "Staff roles now: ops." in output
    assert "Authenticator set up" in output
    assert re.search(
        rf"^{re.escape(phone)}  ops  Asha  {re.escape(email)}  signs in with: authenticator$",
        output,
        re.MULTILINE,
    )
    assert "No longer staff" in output
    assert "Not done: not an Indian mobile number." in output

    async def audit_trail() -> list[tuple[str, str, dict[str, Any]]]:
        app = create_app(settings, clock=clock)
        async with app.router.lifespan_context(app):
            user = await _user(app, phone)
            async with app.state.sessionmaker() as db:
                rows = await db.execute(
                    select(AuditLog.action, AuditLog.actor_type, AuditLog.details)
                    .where(AuditLog.entity_id == str(user.public_id))
                    .order_by(AuditLog.id)
                )
                return [tuple(row) for row in rows]

    assert asyncio.run(audit_trail()) == [
        ("staff.roles_granted", "system", {"roles": ["ops"], "via": "cli"}),
        ("staff.authenticator_enrolled", "system", {"via": "cli"}),
        ("staff.roles_removed", "system", {"roles": ["ops"], "via": "cli"}),
    ]


def test_local_development_signs_staff_in_without_an_authenticator_app(
    make_settings: SettingsFactory,
    database_url: str,
    clock: FrozenClock,
    run: Callable[..., Any],
) -> None:
    settings = make_settings(database_url=database_url)
    phone = _new_phone()
    out = io.StringIO()

    def cli(*argv: str, using: Settings = settings) -> int:
        return manage(list(argv), settings=using, clock=clock, out=out)

    assert cli("staff", "add", phone, "--role", "ops") == 0
    assert cli("staff", "enrol-authenticator", phone, "--without-app") == 0
    # Confirming used this step's code, so this is the next step's, which still counts.
    assert cli("staff", "code", phone) == 0
    code = out.getvalue().strip().splitlines()[-1]
    deployed = settings.model_copy(update={"app_env": "production"})
    assert cli("staff", "code", phone, using=deployed) == 1
    assert cli("staff", "enrol-authenticator", phone, "--without-app", using=deployed) == 1

    async def scenario(app: FastAPI, browser: Browser) -> int:
        browser.cookies[SESSION_COOKIE] = await _session(app, phone)
        response = await browser.request(
            "POST", "/v1/auth/staff/totp", csrf=True, json={"code": code}
        )
        return response.status_code

    assert re.fullmatch(r"[0-9]{6}", code)
    assert run(scenario) == 200
    assert out.getvalue().count("works in local development only") == 2
