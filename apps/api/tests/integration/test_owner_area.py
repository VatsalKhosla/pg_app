"""The owner dashboard (Phase 7, ADR 0063). Done when an owner can run their PG's bookings and
pricing from a phone without calling ops: their own PGs only, their beds, their pricing, their
documents, their bookings with a reminder before each deadline, and their numbers."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.audit import AuditLog
from app.core.calendar import india_date
from app.core.outbox import enqueue
from app.modules.booking.jobs import REMIND_OWNERS
from app.modules.media.domain.assets import Purpose
from tests.authorization import _a_rule
from tests.flags import FixedFlags
from tests.integration.test_booking_confirmation import _booking, _owner_of
from tests.integration.test_booking_holds import _listing
from tests.integration.test_payment_refunds import _paid
from tests.jobs import RecordedTexts, run_due_jobs
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration

MINE = "/v1/owner"


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Any]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def remote_booking(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            await run_due_jobs(ops.app)  # what other tests left waiting
            return await scenario(ops)

        return run_as_staff(settings, remote_booking)

    return run_scenario


async def _actors(ops: Staff, user_id: int) -> set[str]:
    async with ops.app.state.sessionmaker() as db:
        rows = await db.scalars(select(AuditLog.actor_type).where(AuditLog.actor_id == user_id))
        return set(rows)


def test_an_owner_reaches_only_their_own_pgs(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        mine, theirs = await _listing(ops, beds=2), await _listing(ops, beds=1)
        owner = await _owner_of(ops, mine)
        other = theirs["id"]
        other_bed = (await ops.ok("GET", f"/v1/ops/properties/{other}/inventory"))["categories"][0][
            "beds"
        ][0]["id"]
        today = india_date(ops.app.state.clock.now())
        return {
            "pgs": [item["id"] for item in (await owner.ok("GET", f"{MINE}/properties"))["items"]],
            "mine": mine["id"],
            "theirs": [
                (await owner.call(method, path, **extra)).status_code
                for method, path, extra in (
                    ("GET", f"{MINE}/properties/{other}", {}),
                    ("GET", f"{MINE}/properties/{other}/inventory", {}),
                    ("GET", f"{MINE}/properties/{other}/rule-sets", {}),
                    ("GET", f"{MINE}/properties/{other}/market", {}),
                    ("GET", f"{MINE}/properties/{other}/insights", {}),
                    ("GET", f"{MINE}/properties/{other}/documents", {}),
                    (
                        "POST",
                        f"{MINE}/beds/{other_bed}/blocks",
                        {"json": {"kind": "maintenance", "start": str(today), "note": ""}},
                    ),
                )
            ],
        }

    seen = run(scenario)

    assert seen["pgs"] == [seen["mine"]]
    assert seen["theirs"] == [404] * 7


def test_an_owner_runs_their_beds_pricing_and_documents(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        owner = await _owner_of(ops, listing)
        place = listing["id"]
        today = india_date(ops.app.state.clock.now())
        inventory = await owner.ok("GET", f"{MINE}/properties/{place}/inventory")
        bed = inventory["categories"][0]["beds"][0]["id"]
        block = await owner.ok(
            "POST",
            f"{MINE}/beds/{bed}/blocks",
            json={
                "kind": "offline_tenant",
                "start": str(today),
                "end": str(today + timedelta(days=30)),
                "note": "A tenant who came to me directly",
            },
        )
        ended = await owner.ok(
            "POST",
            f"{MINE}/blocks/{block['id']}/end",
            json={"on": str(today + timedelta(days=10))},
        )
        draft = await owner.ok("POST", f"{MINE}/properties/{place}/rule-sets/draft")
        await owner.ok("POST", f"{MINE}/rule-sets/{draft['id']}/rules", json=_a_rule()["json"])
        active = await owner.ok(
            "POST", f"{MINE}/rule-sets/{draft['id']}/activate", json={"note": "Long stays"}
        )
        market = await owner.ok("GET", f"{MINE}/properties/{place}/market")
        document = await owner.ok(
            "POST",
            f"{MINE}/properties/{place}/documents",
            json={"kind": "licence", "media": await owner.media(purpose=Purpose.DOCUMENT)},
        )
        not_a_document = await owner.call(
            "POST",
            f"{MINE}/properties/{place}/documents",
            json={"kind": "licence", "media": await owner.media(purpose=Purpose.LISTING_PHOTO)},
        )
        reviewed = await ops.ok(
            "POST",
            f"/v1/ops/documents/{document['id']}/review",
            json={"accepted": False, "note": "The licence number can't be read."},
        )
        again = await ops.call(
            "POST", f"/v1/ops/documents/{document['id']}/review", json={"accepted": True}
        )
        documents = (await owner.ok("GET", f"{MINE}/properties/{place}/documents"))["items"]
        return {
            "block": (block["kind"], ended["end"]),
            "rules": (active["status"], len(active["rules"])),
            "market": [room["baseRentPaise"] for room in market["rooms"]],
            "document": (document["status"], reviewed["status"]),
            "not a document": not_a_document.json()["code"],
            "again": again.json()["code"],
            "owner sees": [(item["status"], item["note"]) for item in documents],
            "audited as": await _actors(ops, owner.user_id),
        }

    seen = run(scenario)

    assert seen["block"][0] == "offline_tenant"
    assert seen["rules"] == ("active", 1)
    assert seen["market"] == [1_000_000]
    assert seen["document"] == ("submitted", "rejected")
    assert seen["not a document"] == "DOCUMENT_INVALID"
    assert seen["again"] == "INVALID_TRANSITION"
    assert seen["owner sees"] == [("rejected", "The licence number can't be read.")]
    assert "owner" in seen["audited as"]
    assert "staff" not in seen["audited as"]


def test_an_owner_answers_from_their_inbox_and_hears_before_the_deadline(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        owner = await _owner_of(ops, listing)
        _, code, _ = await _paid(ops, listing)
        waiting = (await owner.ok("GET", f"{MINE}/bookings", params={"status": "token_secured"}))[
            "items"
        ]
        booking = await _booking(ops, code)
        assert booking.confirm_by is not None
        texts = RecordedTexts()
        too_soon = booking.confirm_by - timedelta(hours=5)
        ops.app.state.clock.set(too_soon)
        for moment in (too_soon, booking.confirm_by - timedelta(hours=2)):
            ops.app.state.clock.set(moment)
            for _ in range(2):
                async with ops.app.state.sessionmaker() as db, db.begin():
                    await enqueue(db, REMIND_OWNERS, {}, clock=ops.app.state.clock)
                await run_due_jobs(ops.app, texts=texts)
        owner = await _owner_of(ops, listing)
        confirmed = await owner.ok("POST", f"{MINE}/bookings/{code}/confirm")
        return {
            "waiting": [(item["code"], item["confirmBy"] is not None) for item in waiting],
            "reminders": [
                template
                for _, template, values in texts.sent
                if template == "booking_confirm_reminder" and values["code"] == code
            ],
            "confirmed": confirmed["status"],
            "all": [item["code"] for item in (await owner.ok("GET", f"{MINE}/bookings"))["items"]],
            "visits": (await owner.ok("GET", f"{MINE}/visits"))["items"],
        }

    seen = run(scenario)

    assert seen["waiting"]
    assert seen["waiting"][0][1] is True
    # Once, however often the reminder runs, and only within three hours of the deadline.
    assert seen["reminders"] == ["booking_confirm_reminder"]
    assert seen["confirmed"] == "confirmed"
    assert seen["all"][0] == seen["waiting"][0][0]
    assert seen["visits"] == []


def test_an_owner_sees_their_pgs_numbers(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        owner = await _owner_of(ops, listing)
        views = [
            (await ops.call("POST", f"/v1/listings/{listing['slug']}/views")).status_code
            for _ in range(3)
        ]
        nowhere = await ops.call("POST", "/v1/listings/no-such-pg-at-all/views")
        # A booking moving in later holds no bed today; a tenant who came directly does.
        await _paid(ops, listing)
        today = india_date(ops.app.state.clock.now())
        inventory = await owner.ok("GET", f"{MINE}/properties/{listing['id']}/inventory")
        free = [
            bed["id"]
            for bed in inventory["categories"][0]["beds"]
            if not any(each["active"] for each in bed["allocations"])
        ]
        await owner.ok(
            "POST",
            f"{MINE}/beds/{free[0]}/blocks",
            json={"kind": "offline_tenant", "start": str(today), "note": "Came to me directly"},
        )
        insights = await owner.ok(
            "GET", f"{MINE}/properties/{listing['id']}/insights", params={"days": 7}
        )
        return {"views": views, "nowhere": nowhere.status_code, "insights": insights}

    seen = run(scenario)

    insights = seen["insights"]
    assert seen["views"] == [204, 204, 204]
    assert seen["nowhere"] == 404
    assert {
        key: insights[key]
        for key in ("views", "visitRequests", "bookings", "conversionBps", "beds", "bedsTaken")
    } == {
        "views": 3,
        "visitRequests": 0,
        "bookings": 1,
        "conversionBps": None,
        "beds": 2,
        "bedsTaken": 1,
    }
    assert [room["rentPaise"] for room in insights["rooms"]] == [1_000_000]
