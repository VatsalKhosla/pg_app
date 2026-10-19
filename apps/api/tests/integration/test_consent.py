"""Consent end to end (step 1.5, DPDP): signing up needs it, the notice's version is checked, and
optional purposes come and go while the account's own purpose stays.

The app runs against PostgreSQL and Valkey with a frozen clock; a recording sender stands in for
SMS.
"""

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.config import Settings
from app.core.clock import FrozenClock
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import issue_csrf_token
from app.main import create_app
from app.modules.identity.models import User
from tests.conftest import NOTICE_VERSION, TEST_SECRET_KEY

pytestmark = pytest.mark.integration

type Scenario = Callable[[FastAPI, httpx.AsyncClient], Awaitable[Any]]

START = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)
ACCOUNT_ONLY = {"noticeVersion": NOTICE_VERSION, "purposes": ["account"]}


class RecordingSender:
    def __init__(self) -> None:
        self.codes: list[str] = []

    async def send(self, phone_e164: str, code: str) -> None:
        self.codes.append(code)


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Scenario, **settings: object) -> Any:
        app = create_app(
            make_settings(database_url=database_url, redis_url=valkey_url, **settings),
            clock=FrozenClock(START),
        )
        address = f"10.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}"

        async def wrapped() -> Any:
            async with app.router.lifespan_context(app):
                app.state.otp_sender = RecordingSender()
                transport = httpx.ASGITransport(app=app, client=(address, 50_000))
                async with httpx.AsyncClient(
                    transport=transport, base_url="https://api.test"
                ) as client:
                    return await scenario(app, client)

        return asyncio.run(wrapped())

    return run_scenario


def _browser(session: str | None = None) -> dict[str, str]:
    token = issue_csrf_token(TEST_SECRET_KEY.encode(), session)
    cookies = [f"{CSRF_COOKIE}={token}"]
    if session is not None:
        cookies.append(f"{SESSION_COOKIE}={session}")
    return {CSRF_HEADER: token, "Cookie": "; ".join(cookies)}


def _new_mobile() -> str:
    return str(6_000_000_000 + secrets.randbelow(4_000_000_000))


async def _ask_for_code(app: FastAPI, client: httpx.AsyncClient, mobile: str) -> tuple[str, str]:
    response = await client.post(
        "/v1/auth/otp/request",
        json={"phone": mobile, "humanCheckToken": "token"},
        headers=_browser(),
    )
    assert response.status_code == 202
    return response.json()["challengeId"], app.state.otp_sender.codes[-1]


async def _verify(
    client: httpx.AsyncClient, challenge: str, code: str, consent: dict[str, Any] | None
) -> httpx.Response:
    body: dict[str, Any] = {"challengeId": challenge, "code": code}
    if consent is not None:
        body["consent"] = consent
    return await client.post("/v1/auth/otp/verify", json=body, headers=_browser())


async def _accounts(app: FastAPI, mobile: str) -> int:
    async with app.state.sessionmaker() as db:
        count = await db.scalar(
            select(func.count()).select_from(User).where(User.phone_e164 == f"+91{mobile}")
        )
        return count or 0


def _session_of(response: httpx.Response) -> str:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{SESSION_COOKIE}="):
            return header.split(";", 1)[0].split("=", 1)[1]
    raise AssertionError


async def _sign_up(app: FastAPI, client: httpx.AsyncClient) -> str:
    challenge, code = await _ask_for_code(app, client, _new_mobile())
    response = await _verify(client, challenge, code, ACCOUNT_ONLY)
    assert response.status_code == 200
    return _session_of(response)


def test_a_first_sign_in_without_consent_creates_no_account_and_keeps_the_code(
    run: Callable[..., Any],
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        challenge, code = await _ask_for_code(app, client, mobile)

        refused = await _verify(client, challenge, code, None)
        accounts_before = await _accounts(app, mobile)
        accepted = await _verify(client, challenge, code, ACCOUNT_ONLY)

        assert (refused.status_code, refused.json()["code"]) == (400, "CONSENT_REQUIRED")
        assert accounts_before == 0
        assert accepted.status_code == 200
        assert accepted.json()["newUser"] is True
        assert accepted.json()["user"]["consentRequired"] is False
        consents = await client.get(
            "/v1/me/consents", headers={"Cookie": f"{SESSION_COOKIE}={_session_of(accepted)}"}
        )
        assert [
            (consent["purpose"], consent["noticeVersion"], consent["withdrawnAt"])
            for consent in consents.json()["consents"]
        ] == [("account", NOTICE_VERSION, None)]

    run(scenario)


@pytest.mark.parametrize(
    ("consent", "status", "code"),
    [
        ({"noticeVersion": "draft-0", "purposes": ["account"]}, 409, "PRIVACY_NOTICE_CHANGED"),
        ({"noticeVersion": NOTICE_VERSION, "purposes": ["marketing"]}, 400, "CONSENT_REQUIRED"),
        ({"noticeVersion": NOTICE_VERSION, "purposes": []}, 400, "CONSENT_REQUIRED"),
    ],
    ids=["an-old-notice", "only-marketing", "nothing-chosen"],
)
def test_signing_up_needs_consent_to_the_current_notice_for_the_account(
    run: Callable[..., Any], consent: dict[str, Any], status: int, code: str
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        challenge, sent = await _ask_for_code(app, client, mobile)

        refused = await _verify(client, challenge, sent, consent)

        assert (refused.status_code, refused.json()["code"]) == (status, code)
        assert await _accounts(app, mobile) == 0
        # Nothing was used up: the same code still signs up with the right consent.
        assert (await _verify(client, challenge, sent, ACCOUNT_ONLY)).status_code == 200

    run(scenario)


def test_a_returning_person_signs_in_without_being_asked_again(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        mobile = _new_mobile()
        challenge, code = await _ask_for_code(app, client, mobile)
        assert (await _verify(client, challenge, code, ACCOUNT_ONLY)).status_code == 200
        app.state.clock.advance(timedelta(seconds=30))

        challenge, code = await _ask_for_code(app, client, mobile)
        again = await _verify(client, challenge, code, None)

        assert again.status_code == 200
        assert again.json()["newUser"] is False

    run(scenario)


def test_a_new_notice_asks_signed_in_people_to_agree_again(run: Callable[..., Any]) -> None:
    session = run(_sign_up)

    async def under_a_new_notice(_app: FastAPI, client: httpx.AsyncClient) -> None:
        signed_in = {"Cookie": f"{SESSION_COOKIE}={session}"}
        before = (await client.get("/v1/me", headers=signed_in)).json()["consentRequired"]
        old = await client.post(
            "/v1/me/consents",
            json={"noticeVersion": NOTICE_VERSION, "purposes": ["account"]},
            headers=_browser(session),
        )
        agreed = await client.post(
            "/v1/me/consents",
            json={"noticeVersion": "draft-2", "purposes": ["account"]},
            headers=_browser(session),
        )
        after = (await client.get("/v1/me", headers=signed_in)).json()["consentRequired"]

        assert before is True
        assert (old.status_code, old.json()["code"]) == (409, "PRIVACY_NOTICE_CHANGED")
        assert agreed.status_code == 200
        assert after is False

    run(under_a_new_notice, privacy_notice_version="draft-2")


def test_optional_consent_comes_and_goes_and_the_accounts_stays(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        session = await _sign_up(app, client)

        given = await client.post(
            "/v1/me/consents",
            json={"noticeVersion": NOTICE_VERSION, "purposes": ["marketing"]},
            headers=_browser(session),
        )
        withdrawn = await client.delete("/v1/me/consents/marketing", headers=_browser(session))
        withdrawn_again = await client.delete(
            "/v1/me/consents/marketing", headers=_browser(session)
        )
        kept = await client.delete("/v1/me/consents/account", headers=_browser(session))
        history = await client.get(
            "/v1/me/consents", headers={"Cookie": f"{SESSION_COOKIE}={session}"}
        )

        assert given.status_code == 200
        assert (withdrawn.status_code, withdrawn_again.status_code) == (204, 204)
        assert (kept.status_code, kept.json()["code"]) == (409, "CONSENT_NEEDED_FOR_ACCOUNT")
        assert [
            (consent["purpose"], consent["withdrawnAt"] is None)
            for consent in history.json()["consents"]
        ] == [("account", True), ("marketing", False)]

    run(scenario)


def test_the_privacy_notice_says_its_version_and_which_purposes_are_needed(
    run: Callable[..., Any],
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> None:
        response = await client.get("/v1/privacy-notice")

        assert response.json() == {
            "version": NOTICE_VERSION,
            "purposes": [
                {"purpose": "account", "required": True},
                {"purpose": "marketing", "required": False},
            ],
        }

    run(scenario)
