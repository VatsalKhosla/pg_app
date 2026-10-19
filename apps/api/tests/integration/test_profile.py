"""The profile people keep themselves (step 1.6): only the fields sent change, null clears an
optional one, and the name can change but not go."""

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.core.actor import Role
from app.core.clock import FrozenClock
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import issue_csrf_token
from app.main import create_app
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import SessionService
from tests.conftest import TEST_SECRET_KEY

pytestmark = pytest.mark.integration

type Scenario = Callable[[FastAPI, httpx.AsyncClient, str], Awaitable[Any]]


@pytest.fixture
def run(make_settings: Callable[..., Settings], database_url: str) -> Callable[..., Any]:
    """Run a scenario for someone signed in, with their session token."""

    def run_scenario(scenario: Scenario) -> Any:
        app = create_app(
            make_settings(database_url=database_url),
            clock=FrozenClock(datetime(2027, 7, 14, 10, 0, tzinfo=UTC)),
        )

        async def wrapped() -> Any:
            async with app.router.lifespan_context(app):
                phone = f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"
                async with app.state.sessionmaker() as db:
                    async with db.begin():
                        user = await UserRepository(db).add(phone_e164=phone, roles=[Role.STUDENT])
                    session = await SessionService(db, app.state.clock).start(
                        user.id, kind=SessionKind.USER, ip_address=None, user_agent=None
                    )
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="https://api.test"
                ) as client:
                    return await scenario(app, client, session.token)

        return asyncio.run(wrapped())

    return run_scenario


def _as(session: str) -> dict[str, str]:
    csrf = issue_csrf_token(TEST_SECRET_KEY.encode(), session)
    return {
        CSRF_HEADER: csrf,
        "Cookie": f"{SESSION_COOKIE}={session}; {CSRF_COOKIE}={csrf}",
    }


async def _change(client: httpx.AsyncClient, session: str, body: object) -> httpx.Response:
    return await client.patch("/v1/me", json=body, headers=_as(session))


def test_only_the_fields_sent_change(run: Callable[..., Any]) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient, session: str) -> None:
        full = await _change(
            client,
            session,
            {"name": "  Asha Verma ", "collegeOrWorkplace": "A college", "gender": "female"},
        )
        partial = await _change(client, session, {"collegeOrWorkplace": "A workplace"})
        cleared = await _change(client, session, {"collegeOrWorkplace": None, "gender": None})
        me = await client.get("/v1/me", headers=_as(session))

        assert full.status_code == 200
        assert (full.json()["name"], full.json()["gender"]) == ("Asha Verma", "female")
        assert partial.json()["name"] == "Asha Verma"
        assert partial.json()["collegeOrWorkplace"] == "A workplace"
        assert (cleared.json()["collegeOrWorkplace"], cleared.json()["gender"]) == (None, None)
        assert me.json()["name"] == "Asha Verma"

    run(scenario)


@pytest.mark.parametrize(
    "body",
    [
        {"name": None},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 81},
        {"name": "Asha\nVerma"},
        {"collegeOrWorkplace": "x" * 121},
        {"gender": "unknown"},
        {"role": "admin"},
    ],
    ids=[
        "no-name",
        "empty-name",
        "blank-name",
        "long-name",
        "control-character",
        "long-place",
        "unknown-gender",
        "an-unknown-field",
    ],
)
def test_a_bad_change_is_a_field_error_and_changes_nothing(
    run: Callable[..., Any], body: dict[str, object]
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient, session: str) -> None:
        await _change(client, session, {"name": "Asha"})

        refused = await _change(client, session, body)
        me = await client.get("/v1/me", headers=_as(session))

        assert (refused.status_code, refused.json()["code"]) == (422, "VALIDATION_ERROR")
        assert me.json()["name"] == "Asha"
        assert me.json()["roles"] == ["student"]

    run(scenario)
