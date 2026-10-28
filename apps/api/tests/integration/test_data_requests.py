"""Data requests end to end (step 1.5, DPDP): an export built by the worker and downloaded by its
owner only, deletions in the ops queue, and export files deleted by the retention job.

The app runs against PostgreSQL and Valkey with a frozen clock. The worker runs in the test, as
the worker process would, with the real job registry.
"""

import asyncio
import json
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.config import Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from app.core.clock import FrozenClock
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import issue_csrf_token
from app.core.outbox import OutboxWorker
from app.core.web_cache import NoWebCache
from app.jobs import RETENTION_RULES, build_registry
from app.main import create_app
from app.modules.compliance.retention import run_retention
from app.modules.identity.domain.consent import ConsentPurpose
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.repository import ConsentRepository, UserRepository
from app.modules.identity.service import SessionService
from tests.conftest import NOTICE_VERSION, TEST_SECRET_KEY
from tests.storage import BUCKETS, MemoryStorage

pytestmark = pytest.mark.integration

type Scenario = Callable[[FastAPI, httpx.AsyncClient], Awaitable[Any]]

START = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Scenario) -> Any:
        app = create_app(
            make_settings(database_url=database_url, redis_url=valkey_url),
            clock=FrozenClock(START),
        )
        address = f"10.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}"

        async def wrapped() -> Any:
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app, client=(address, 50_000))
                async with httpx.AsyncClient(
                    transport=transport, base_url="https://api.test"
                ) as client:
                    return await scenario(app, client)

        return asyncio.run(wrapped())

    return run_scenario


async def _person(
    app: FastAPI, role: Role = Role.STUDENT, kind: SessionKind = SessionKind.USER
) -> tuple[str, str]:
    """Someone signed up with consent and signed in; returns their phone and session token."""
    phone = f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"
    async with app.state.sessionmaker() as db:
        async with db.begin():
            user = await UserRepository(db).add(phone_e164=phone, roles=(role,))
            await ConsentRepository(db).grant(
                user.id,
                [ConsentPurpose.ACCOUNT],
                notice_version=NOTICE_VERSION,
                now=app.state.clock.now(),
            )
        issued = await SessionService(db, app.state.clock).start(
            user.id, kind=kind, ip_address="203.0.113.7", user_agent="Mozilla/5.0"
        )
    return phone, issued.token


def _as(session: str, *, csrf: bool = False) -> dict[str, str]:
    cookies = [f"{SESSION_COOKIE}={session}"]
    headers: dict[str, str] = {}
    if csrf:
        token = issue_csrf_token(TEST_SECRET_KEY.encode(), session)
        cookies.append(f"{CSRF_COOKIE}={token}")
        headers[CSRF_HEADER] = token
    headers["Cookie"] = "; ".join(cookies)
    return headers


async def _ask(client: httpx.AsyncClient, session: str, kind: str) -> httpx.Response:
    return await client.post(
        "/v1/me/data-requests", json={"kind": kind}, headers=_as(session, csrf=True)
    )


async def _run_worker(app: FastAPI) -> None:
    """Run every due job, as the worker process would."""
    worker = OutboxWorker(
        sessionmaker=app.state.sessionmaker,
        registry=build_registry(storage=MemoryStorage(), buckets=BUCKETS, web_cache=NoWebCache()),
        clock=app.state.clock,
        worker_id="test",
        batch_size=50,
    )
    while await worker.run_once():
        pass


async def _my_requests(client: httpx.AsyncClient, session: str) -> list[dict[str, Any]]:
    response = await client.get("/v1/me/data-requests", headers=_as(session))
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def test_an_export_is_built_by_the_worker_and_downloaded_by_its_owner_only(
    run: Callable[..., Any],
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        phone, session = await _person(app)
        _, someone_else = await _person(app)
        _, ops = await _person(app, Role.OPS, SessionKind.STAFF)

        asked = await _ask(client, session, "export")
        await _run_worker(app)
        [request] = await _my_requests(client, session)
        url = f"/v1/me/data-requests/{request['id']}/file"
        downloaded = await client.get(url, headers=_as(session))
        by_someone_else = await client.get(url, headers=_as(someone_else))
        by_ops = await client.get(url, headers=_as(ops))

        assert (asked.status_code, asked.json()["status"]) == (202, "received")
        assert request["status"] == "ready"
        assert request["expiresAt"] == (START + timedelta(days=7)).isoformat().replace(
            "+00:00", "Z"
        )
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"] == "application/json"
        assert downloaded.headers["cache-control"] == "no-store"
        assert downloaded.headers["content-disposition"] == (
            'attachment; filename="my-data-2027-07-14.json"'
        )
        data = json.loads(downloaded.content)
        assert data["account"]["phone"] == phone
        assert [consent["purpose"] for consent in data["consents"]] == ["account"]
        assert data["sessions"][0]["ipAddress"] == "203.0.113.7"
        assert [item["kind"] for item in data["dataRequests"]] == ["export"]
        # Nothing secret leaves: no session tokens or their hashes.
        assert session not in downloaded.text
        assert "tokenHash" not in downloaded.text
        assert (by_someone_else.status_code, by_ops.status_code) == (404, 404)

    run(scenario)


def test_asking_again_while_a_request_is_open_answers_the_open_one(
    run: Callable[..., Any],
) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        _, session = await _person(app)

        deletions = [await _ask(client, session, "deletion") for _ in range(2)]
        exports = [await _ask(client, session, "export") for _ in range(2)]

        assert deletions[0].json()["id"] == deletions[1].json()["id"]
        assert exports[0].json()["id"] == exports[1].json()["id"]
        assert len(await _my_requests(client, session)) == 2

    run(scenario)


def test_staff_resolve_deletion_requests_from_the_queue(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        phone, session = await _person(app)
        _, ops = await _person(app, Role.OPS, SessionKind.STAFF)
        deletion = (await _ask(client, session, "deletion")).json()
        export = (await _ask(client, session, "export")).json()

        waiting: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:  # other tests' requests come first: page on to the end
            params = {"status": "received", "limit": "50"} | (
                {} if cursor is None else {"cursor": cursor}
            )
            page = (
                await client.get("/v1/ops/data-requests", params=params, headers=_as(ops))
            ).json()
            waiting.extend(page["items"])
            cursor = page["nextCursor"]
            if cursor is None:
                break
        resolution = {"outcome": "rejected", "note": "The account has an active booking."}
        resolved = await client.post(
            f"/v1/ops/data-requests/{deletion['id']}/resolve",
            json=resolution,
            headers=_as(ops, csrf=True),
        )
        twice = await client.post(
            f"/v1/ops/data-requests/{deletion['id']}/resolve",
            json=resolution,
            headers=_as(ops, csrf=True),
        )
        an_export = await client.post(
            f"/v1/ops/data-requests/{export['id']}/resolve",
            json=resolution,
            headers=_as(ops, csrf=True),
        )
        seen_by_the_person = {item["id"]: item for item in await _my_requests(client, session)}

        assert {item["id"] for item in waiting} >= {deletion["id"], export["id"]}
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "rejected"
        assert resolved.json()["requester"]["phone"] == phone
        assert (twice.status_code, twice.json()["code"]) == (409, "INVALID_TRANSITION")
        assert (an_export.status_code, an_export.json()["code"]) == (409, "INVALID_TRANSITION")
        assert seen_by_the_person[deletion["id"]]["note"] == "The account has an active booking."
        async with app.state.sessionmaker() as db:
            actions = list(
                await db.scalars(
                    select(AuditLog.action).where(AuditLog.entity_id == deletion["id"])
                )
            )
        assert actions == ["data_request.resolved"]

    run(scenario)


def test_the_retention_job_deletes_export_files_after_a_week(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> None:
        _, session = await _person(app)
        await _ask(client, session, "export")
        await _run_worker(app)
        [request] = await _my_requests(client, session)
        url = f"/v1/me/data-requests/{request['id']}/file"

        app.state.clock.advance(timedelta(days=6, hours=23))
        async with app.state.sessionmaker() as db, db.begin():
            early = await run_retention(db, app.state.clock, RETENTION_RULES)
        still_there = await client.get(url, headers=_as(session))
        app.state.clock.advance(timedelta(hours=1))
        async with app.state.sessionmaker() as db, db.begin():
            on_time = await run_retention(db, app.state.clock, RETENTION_RULES)
        gone = await client.get(url, headers=_as(session))

        assert set(early) == {rule.name for rule in RETENTION_RULES}
        assert still_there.status_code == 200
        assert on_time["data_exports"] >= 1
        assert gone.status_code == 404
        assert (await _my_requests(client, session))[0]["status"] == "expired"

    run(scenario)
