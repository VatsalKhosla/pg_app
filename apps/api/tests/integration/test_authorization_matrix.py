"""Every route called by every kind of caller, as tests/authorization.py says (step 1.4).

The app runs against PostgreSQL and Valkey. Each call gets a fresh session for its caller (some
routes end it), a valid CSRF token, and someone else's records in its path.
"""

import asyncio
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

import httpx
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.core.actor import Role
from app.core.clock import FrozenClock
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import issue_csrf_token
from app.main import create_app
from app.modules.compliance.domain.requests import EXPORT_TTL, DataRequestKind, DataRequestStatus
from app.modules.compliance.repository import DataExportRepository, DataRequestRepository
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import SessionService
from tests.authorization import CALLERS, MATRIX
from tests.conftest import TEST_SECRET_KEY

pytestmark = pytest.mark.integration

# The account behind each signed-in caller, and the kind of session it signs in with.
SIGNED_IN: Final = {
    "student": (Role.STUDENT, SessionKind.USER),
    "parent": (Role.PARENT, SessionKind.USER),
    "owner": (Role.OWNER, SessionKind.USER),
    "admin_by_phone": (Role.ADMIN, SessionKind.USER),
    "field_agent": (Role.FIELD_AGENT, SessionKind.STAFF),
    "ops": (Role.OPS, SessionKind.STAFF),
    "admin": (Role.ADMIN, SessionKind.STAFF),
}
SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})


class _NoSms:
    async def send(self, phone_e164: str, code: str) -> None:
        return None


def _new_phone() -> str:
    return f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"


async def _add_user(app: FastAPI, role: Role) -> int:
    async with app.state.sessionmaker() as db, db.begin():
        return (await UserRepository(db).add(phone_e164=_new_phone(), roles=(role,))).id


async def _start_session(app: FastAPI, user_id: int, kind: SessionKind) -> tuple[str, str]:
    """A new session's token and public id."""
    async with app.state.sessionmaker() as db:
        issued = await SessionService(db, app.state.clock).start(
            user_id, kind=kind, ip_address=None, user_agent=None
        )
    return issued.token, str(issued.public_id)


async def _someone_elses_request(app: FastAPI, kind: DataRequestKind) -> str:
    """A data request of someone else's: an export ready to download, or an open deletion."""
    user_id = await _add_user(app, Role.STUDENT)
    now = app.state.clock.now()
    async with app.state.sessionmaker() as db, db.begin():
        request = await DataRequestRepository(db).insert_open(user_id, kind, now=now)
        assert request is not None
        if kind is DataRequestKind.EXPORT:
            await DataExportRepository(db).put(request.id, b"{}")
            request.status = DataRequestStatus.READY
            request.expires_at = now + EXPORT_TTL
        return str(request.public_id)


async def _path_value(app: FastAPI, kind: str) -> str:
    match kind:
        case "someone_elses_session":
            user_id = await _add_user(app, Role.STUDENT)
            return (await _start_session(app, user_id, SessionKind.USER))[1]
        case "someone_elses_export":
            return await _someone_elses_request(app, DataRequestKind.EXPORT)
        case "someone_elses_deletion_request":
            return await _someone_elses_request(app, DataRequestKind.DELETION)
        case "an_optional_purpose":
            return "marketing"
        case _:
            msg = f"no way to make {kind!r}"
            raise LookupError(msg)


def _headers(token: str | None, *, unsafe: bool) -> dict[str, str]:
    cookies = [] if token is None else [f"{SESSION_COOKIE}={token}"]
    headers: dict[str, str] = {}
    if unsafe:
        csrf = issue_csrf_token(TEST_SECRET_KEY.encode(), token)
        cookies.append(f"{CSRF_COOKIE}={csrf}")
        headers[CSRF_HEADER] = csrf
    if cookies:
        headers["Cookie"] = "; ".join(cookies)
    return headers


def test_every_caller_gets_what_the_authorization_matrix_says(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> None:
    app = create_app(
        make_settings(database_url=database_url, redis_url=valkey_url),
        clock=FrozenClock(datetime(2027, 7, 14, 10, 0, tzinfo=UTC)),
    )
    address = f"10.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}"

    async def call_everything() -> list[str]:
        async with app.router.lifespan_context(app):
            app.state.otp_sender = _NoSms()
            accounts = {
                caller: (await _add_user(app, role), kind)
                for caller, (role, kind) in SIGNED_IN.items()
            }
            transport = httpx.ASGITransport(app=app, client=(address, 50_000))
            wrong: list[str] = []
            async with httpx.AsyncClient(
                transport=transport, base_url="https://api.test"
            ) as client:
                for (method, path), rule in MATRIX.items():
                    for caller in CALLERS:
                        values = {
                            name: await _path_value(app, kind) for name, kind in rule.path.items()
                        }
                        url = path.format(**values)
                        token = None
                        if caller in accounts:
                            token, _ = await _start_session(app, *accounts[caller])
                        client.cookies.clear()
                        response = await client.request(
                            method,
                            url,
                            headers=_headers(token, unsafe=method not in SAFE_METHODS),
                            **rule.request(),
                        )
                        expected = rule.expected[caller]
                        if response.status_code != expected:
                            wrong.append(
                                f"{method} {path} as {caller}: {response.status_code}, "
                                f"expected {expected} ({response.text[:100]})"
                            )
            return wrong

    assert asyncio.run(call_everything()) == []
