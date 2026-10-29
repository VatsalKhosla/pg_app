"""Grievances end to end in the API (step 3.8, ADR 0034): anyone complains and gets a ticket
number; the grievance officer's team acknowledges within 48 hours and resolves within a month; a
signed-in complainant is texted at each step and sees the replies; and the abuse guards."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.config import Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER
from app.core.csrf import issue_csrf_token
from app.core.ids import TICKET_NUMBER_PATTERN
from app.jobs import EXPORTERS
from app.modules.compliance.service import grievances_part
from app.modules.identity.domain.sessions import SessionKind
from tests.conftest import TEST_SECRET_KEY
from tests.integration.test_otp_sign_in import RefusingHumanCheck
from tests.jobs import RecordedTexts, run_due_jobs
from tests.staff_api import NOW, Staff, phone, run_as_staff, sign_in

pytestmark = pytest.mark.integration

GRIEVANCES = "/v1/grievances"


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


async def _signed_out(
    app: FastAPI, body: dict[str, Any], *, ip: str = "203.0.113.7"
) -> httpx.Response:
    """A complaint from someone signed out, from ``ip`` (a documentation address)."""
    csrf = issue_csrf_token(TEST_SECRET_KEY.encode(), None)
    transport = httpx.ASGITransport(app=app, client=(ip, 50_000))
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        return await client.post(
            GRIEVANCES, json=body, headers={CSRF_HEADER: csrf, "Cookie": f"{CSRF_COOKIE}={csrf}"}
        )


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _about(texts: RecordedTexts, ticket: str) -> list[tuple[str, str, dict[str, str]]]:
    """The texts sent about one grievance: the outbox is shared with other tests' jobs."""
    return [sent for sent in texts.sent if sent[2].get("ticket") == ticket]


COMPLAINT: dict[str, Any] = {
    "category": "listing",
    "reference": "Fictional Residency",
    "details": "The photos showed a window; the room has none.",
    "humanCheckToken": "token",
}


def test_anyone_complains_and_the_officer_acknowledges_and_resolves_it(  # noqa: PLR0915 - one grievance's whole life, in order
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        clock = ops.app.state.clock
        texts = RecordedTexts()
        student = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        seen: dict[str, Any] = {}
        # Signed out: a name and a phone or an email are needed.
        missing = await _signed_out(ops.app, COMPLAINT)
        seen["missing"] = missing.json()
        typed = phone()
        seen["signed out"] = (
            await _signed_out(ops.app, COMPLAINT | {"name": "A Parent", "phone": typed})
        ).json()
        # Signed in: the account is the contact, whatever phone is sent.
        seen["signed in"] = await student.ok(
            "POST",
            GRIEVANCES,
            json=COMPLAINT | {"category": "visit", "phone": phone(), "details": "Nobody came."},
        )
        ticket = seen["signed in"]["ticketNumber"]
        await run_due_jobs(ops.app, texts=texts)
        seen["texted on receipt"] = _about(texts, ticket)
        # The queue: oldest first, the order they fall due. Other tests' grievances share it.
        seen["queue"] = await ops.ok(
            "GET", "/v1/ops/grievances", params={"status": "received", "limit": 50}
        )
        seen["signed in, queued"] = await ops.ok("GET", f"/v1/ops/grievances/{ticket}")
        seen["signed out, queued"] = await ops.ok(
            "GET", f"/v1/ops/grievances/{seen['signed out']['ticketNumber']}"
        )
        # Two days and a minute later, it's late until acknowledged.
        clock.set(NOW + timedelta(hours=48, minutes=1))
        ops = await sign_in(ops.app, ops.client, Role.OPS)
        seen["late"] = await ops.ok("GET", f"/v1/ops/grievances/{ticket.lower()}")
        seen["acknowledged"] = await ops.ok(
            "POST",
            f"/v1/ops/grievances/{ticket}/acknowledge",
            json={"reply": "  Sorry. Our ops lead will call you today.  "},
        )
        await run_due_jobs(ops.app, texts=texts)
        seen["again"] = (
            await ops.call(
                "POST", f"/v1/ops/grievances/{ticket}/acknowledge", json={"reply": "Again."}
            )
        ).json()["code"]
        seen["resolved"] = await ops.ok(
            "POST",
            f"/v1/ops/grievances/{ticket}/resolve",
            json={"resolution": "We rebooked the visit with another agent."},
        )
        await run_due_jobs(ops.app, texts=texts)
        seen["texts"] = _about(texts, ticket)
        seen["mine"] = await student.ok("GET", "/v1/me/grievances")
        # Straight from received to resolved acknowledges it too.
        other = seen["signed out"]["ticketNumber"]
        seen["resolved at once"] = await ops.ok(
            "POST",
            f"/v1/ops/grievances/{other}/resolve",
            json={"resolution": "We removed the listing's wrong photo."},
        )
        seen["unknown"] = (await ops.call("GET", "/v1/ops/grievances/GR-00000000")).status_code
        seen["not a ticket"] = (await ops.call("GET", "/v1/ops/grievances/nonsense")).status_code
        async with ops.app.state.sessionmaker() as db:
            rows = await db.scalars(
                select(AuditLog.action).where(
                    AuditLog.entity_type == "grievance", AuditLog.entity_id == ticket
                )
            )
            seen["audited"] = list(rows)
        seen["typed"] = typed
        return seen

    seen = run(scenario)

    missing = seen["missing"]
    assert missing["code"] == "VALIDATION_ERROR"
    assert [error["pointer"] for error in missing["errors"]] == ["/name", "/phone"]
    receipt = seen["signed out"]
    assert TICKET_NUMBER_PATTERN.fullmatch(receipt["ticketNumber"])
    received = _when(receipt["receivedAt"])
    assert _when(receipt["acknowledgeBy"]) - received == timedelta(hours=48)
    # 14 July 2027 in India: resolved by 14 August.
    assert _when(receipt["resolveBy"]) - received == timedelta(days=31)
    # Texts only to the signed-in complainant's own phone, never a number someone typed.
    assert [template for _, template, _ in seen["texted on receipt"]] == ["grievance_received"]
    [(texted_phone, _, values)] = seen["texted on receipt"]
    assert texted_phone != f"+91{seen['typed']}"
    assert (values["ticket"], values["acknowledge_by"], values["resolve_by"]) == (
        seen["signed in"]["ticketNumber"],
        "Fri 16 Jul",
        "Sat 14 Aug",
    )
    queue = seen["queue"]["items"]
    assert {item["status"] for item in queue} == {"received"}
    assert [item["receivedAt"] for item in queue] == sorted(item["receivedAt"] for item in queue)
    mine_queued = seen["signed in, queued"]
    assert mine_queued["complainant"]["account"] is not None
    assert mine_queued["complainant"]["phone"] == texted_phone
    assert mine_queued["late"] is False
    assert mine_queued["nextStatuses"] == ["acknowledged", "resolved"]
    signed_out = seen["signed out, queued"]["complainant"]
    assert signed_out == {
        "name": "A Parent",
        "phone": f"+91{seen['typed']}",
        "email": None,
        "account": None,
    }
    assert seen["late"]["late"] is True
    assert seen["acknowledged"]["reply"] == "Sorry. Our ops lead will call you today."
    assert seen["acknowledged"]["late"] is False
    assert seen["again"] == "INVALID_TRANSITION"
    assert seen["resolved"]["status"] == "resolved"
    assert seen["resolved"]["nextStatuses"] == []
    assert [template for _, template, _ in seen["texts"]] == [
        "grievance_received",
        "grievance_acknowledged",
        "grievance_resolved",
    ]
    at_once = seen["resolved at once"]
    assert at_once["acknowledgedAt"] == at_once["resolvedAt"]
    assert at_once["reply"] == ""
    assert (seen["unknown"], seen["not a ticket"]) == (404, 404)
    assert seen["audited"] == ["grievances.acknowledged", "grievances.resolved"]
    [mine] = seen["mine"]["items"]
    assert (mine["status"], mine["category"], mine["details"]) == (
        "resolved",
        "visit",
        "Nobody came.",
    )
    assert mine["reply"].startswith("Sorry.")
    assert mine["resolution"] == "We rebooked the visit with another agent."


def test_the_form_refuses_bots_and_floods_and_exports_hold_the_complaints(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        body = COMPLAINT | {"name": "A Parent", "email": "parent@example.com"}
        seen: dict[str, Any] = {}
        ops.app.state.human_check = RefusingHumanCheck()
        seen["bot"] = (await _signed_out(ops.app, body)).json()["code"]
        # Signed in, there is no human check.
        student = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        created = await student.call("POST", GRIEVANCES, json=COMPLAINT)
        seen["student"] = created.status_code
        # Resolved before its texts go: the receipt no longer applies, the resolution does.
        await ops.ok(
            "POST",
            f"/v1/ops/grievances/{created.json()['ticketNumber']}/resolve",
            json={"resolution": "We called and sorted it out."},
        )
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        seen["texts"] = [
            template for _, template, _ in _about(texts, created.json()["ticketNumber"])
        ]
        ops.app.state.human_check = _Passing()
        ip = "198.51.100.23"
        seen["statuses"] = [(await _signed_out(ops.app, body, ip=ip)).status_code for _ in range(6)]
        seen["elsewhere"] = (await _signed_out(ops.app, body, ip="198.51.100.24")).status_code
        async with ops.app.state.sessionmaker() as db, db.begin():
            seen["export"] = await grievances_part(db, student.user_id)
            seen["no export"] = await grievances_part(db, ops.user_id)
        return seen

    seen = run(scenario)

    assert seen["bot"] == "HUMAN_CHECK_FAILED"
    assert seen["student"] == 201
    assert seen["texts"] == ["grievance_resolved"]
    assert seen["statuses"] == [201] * 5 + [429]
    assert seen["elsewhere"] == 201
    assert grievances_part in EXPORTERS
    [exported] = seen["export"]["grievances"]
    assert (exported["category"], exported["status"]) == ("listing", "resolved")
    assert exported["resolution"] == "We called and sorted it out."
    assert seen["no export"] == {}


class _Passing:
    async def verify(self, token: str, *, remote_ip: str | None, action: str) -> bool:
        return action == "grievance"
