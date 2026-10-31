"""Holds in the API and the database (step 5.3, ADR 0046):
- a student holds a bed at their quote's price, in a partly held room first;
- a retry with the same Idempotency-Key gets the first answer back;
- what a hold refuses, and why;
- a hold past its expiry frees its bed for the next student;
- fifty students asking at once for the last bed hold it once."""

import asyncio
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from app.core.idempotency import REPLAYED_HEADER
from app.core.ids import new_booking_code
from app.core.outbox import OutboxJob
from app.modules.booking.models import Booking, BookingEventRecord
from app.modules.catalog.models import Bed
from app.modules.identity.domain.sessions import SessionKind
from app.modules.inventory.models import InventoryAllocation
from app.modules.inventory.service import ALLOCATIONS_CHANGED
from tests.flags import FixedFlags
from tests.integration.test_pricing_quotes import _anyone
from tests.integration.test_search import _category, _publish, _token
from tests.staff_api import NOW, Staff, run_as_staff, sign_in, spot

pytestmark = pytest.mark.integration

HOLDS = "/v1/bookings"
QUOTES = "/v1/quotes"
MOVE_IN = date(2027, 8, 20)


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        # Room for fifty requests at once, each in a transaction of its own.
        settings = make_settings(
            database_url=database_url, redis_url=valkey_url, db_pool_size=30, db_max_overflow=30
        )

        async def remote_booking(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            return await scenario(ops)

        return run_as_staff(settings, remote_booking)

    return run_scenario


async def _student(ops: Staff) -> Staff:
    return await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)


async def _listing(ops: Staff, *, beds: int, locality: str = "satya-niketan") -> dict[str, Any]:
    return await _publish(
        ops,
        name=f"Booking PG {_token()}",
        at=spot(700),
        locality=locality,
        categories=[_category("double", 10_000, beds=beds)],
    )


def _quote_body(category: str) -> dict[str, Any]:
    return {"roomCategory": category, "moveIn": MOVE_IN.isoformat(), "stayMonths": 11}


async def _quote(student: Staff, category: str) -> dict[str, Any]:
    """The student's quote, asked for from an address of its own: quotes are limited per
    address and minute, and every test's clock stands at the same minute."""
    address = f"198.51.{secrets.randbelow(256)}.{secrets.randbelow(254) + 1}"
    transport = httpx.ASGITransport(app=student.app, client=(address, 50_000))
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        response = await client.post(QUOTES, json=_quote_body(category), headers=student._headers())
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def _hold(student: Staff, quote: str, *, key: str | None = None) -> httpx.Response:
    return await student.call(
        "POST",
        HOLDS,
        json={"quote": quote},
        headers={"Idempotency-Key": key or f"hold-{uuid.uuid4().hex}"},
    )


def _category_of(listing: dict[str, Any]) -> str:
    category: str = listing["categories"][0]["id"]
    return category


async def _beds(ops: Staff, listing: dict[str, Any]) -> dict[str, int]:
    """The listing's beds by room and label ("101 A"), as internal ids."""
    found = {}
    async with ops.app.state.sessionmaker() as db:
        for room in listing["categories"][0]["rooms"]:
            for bed in room["beds"]:
                found[f"{room['label']} {bed['label']}"] = await db.scalar(
                    select(Bed.id).where(Bed.public_id == uuid.UUID(bed["id"]))
                )
    return found


async def _booking(ops: Staff, code: str) -> Booking:
    async with ops.app.state.sessionmaker() as db:
        found: Booking | None = await db.scalar(select(Booking).where(Booking.code == code))
        assert found is not None
        return found


def test_a_student_holds_a_bed_at_their_quotes_price(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        path = f"/v1/ops/room-categories/{_category_of(listing)}/rooms"
        await ops.ok("POST", path, json={"label": "102", "beds": 2})
        listing = await ops.ok("GET", f"/v1/ops/properties/{listing['id']}")
        beds = await _beds(ops, listing)
        # Someone the owner placed holds bed 102 A, so 102 is the partly held room.
        await ops.ok(
            "POST",
            f"/v1/ops/beds/{listing['categories'][0]['rooms'][1]['beds'][0]['id']}/blocks",
            json={"kind": "offline_tenant", "start": "2027-08-01", "end": None},
        )
        student = await _student(ops)
        quote = await _quote(student, _category_of(listing))
        held = await _hold(student, quote["id"])
        code = held.json()["code"]
        booking = await _booking(ops, code)
        async with ops.app.state.sessionmaker() as db:
            allocation = await db.scalar(
                select(InventoryAllocation).where(InventoryAllocation.booking_id == booking.id)
            )
            events = (
                await db.scalars(
                    select(BookingEventRecord).where(BookingEventRecord.booking_id == booking.id)
                )
            ).all()
            audited = await db.scalar(
                select(func.count()).where(
                    AuditLog.entity_type == "booking", AuditLog.entity_id == code
                )
            )
            refreshes = await db.scalar(
                select(func.count()).where(
                    OutboxJob.kind == ALLOCATIONS_CHANGED,
                    OutboxJob.payload["property_id"].as_integer() == booking.property_id,
                )
            )
        other = await _student(ops)
        return {
            "held": held,
            "quote": quote,
            "bed": next(name for name, bed in beds.items() if bed == booking.bed_id),
            "booking": booking,
            "allocation": allocation,
            "events": [(e.event, e.from_status, e.to_status, e.actor_type) for e in events],
            "student": student.user_id,
            "audited": audited,
            "refreshes": refreshes,
            "mine": await student.ok("GET", f"{HOLDS}/{code.lower()}"),
            "theirs": (await other.call("GET", f"{HOLDS}/{code}")).status_code,
            "nonsense": (await student.call("GET", f"{HOLDS}/not-a-code")).status_code,
        }

    seen = run(scenario)

    held, quote, booking = seen["held"], seen["quote"], seen["booking"]
    assert held.status_code == 201, held.text
    body = held.json()
    assert body["code"].startswith("BK-")
    assert [(step["event"], step["status"], step["by"]) for step in body["timeline"]] == [
        ("hold", "held", "student")
    ]
    assert body | {"code": None, "createdAt": None, "timeline": None} == {
        "code": None,
        "timeline": None,
        # Nothing has been paid yet, so cancelling gives nothing back.
        "cancellation": {"refundPaise": 0, "late": False},
        "status": "held",
        "property": {
            "slug": quote["place"]["slug"],
            "name": quote["place"]["name"],
            "locality": "Satya Niketan",
        },
        "roomType": "Double sharing",
        "moveIn": "2027-08-20",
        "stayMonths": 11,
        "plannedMoveOut": "2028-07-20",
        "holdExpiresAt": (NOW + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
        "confirmBy": None,
        "monthlyRentPaise": quote["monthlyRentPaise"],
        "tokenPaise": quote["tokenPaise"],
        "dueAtMoveInPaise": quote["dueAtMoveInPaise"],
        "depositPaise": quote["depositPaise"],
        "monthlyChargesPaise": quote["monthlyChargesPaise"],
        "oneTimeChargesPaise": quote["oneTimeChargesPaise"],
        "createdAt": None,
    }
    assert seen["mine"] == body
    assert (seen["theirs"], seen["nonsense"]) == (404, 404)
    # Room 102 is partly held, so it goes first; 101's two beds stay free together.
    assert seen["bed"] == "102 B"
    assert (booking.student_id, booking.version, booking.channel) == (seen["student"], 1, "remote")
    allocation = seen["allocation"]
    assert allocation.is_active
    assert allocation.kind == "booking"
    assert (allocation.period.lower, allocation.period.upper) == (MOVE_IN, date(2028, 7, 20))
    assert seen["events"] == [("hold", None, "held", "student")]
    assert seen["audited"] == 1
    assert seen["refreshes"] >= 1


def test_a_retry_with_the_same_key_gets_the_first_answer(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        student = await _student(ops)
        quote = await _quote(student, _category_of(listing))
        key = f"hold-{uuid.uuid4().hex}"
        first = await _hold(student, quote["id"], key=key)
        again = await _hold(student, quote["id"], key=key)
        other = await _quote(student, _category_of(listing))
        reused = await _hold(student, other["id"], key=key)
        keyless = await student.call("POST", HOLDS, json={"quote": quote["id"]})
        async with ops.app.state.sessionmaker() as db:
            bookings = await db.scalar(
                select(func.count()).where(Booking.student_id == student.user_id)
            )
        return {
            "first": first,
            "again": again,
            "reused": reused.json()["code"],
            "keyless": keyless.json()["code"],
            "bookings": bookings,
        }

    seen = run(scenario)

    assert (seen["first"].status_code, seen["again"].status_code) == (201, 201)
    assert seen["again"].json() == seen["first"].json()
    assert REPLAYED_HEADER.lower() not in seen["first"].headers
    assert seen["again"].headers[REPLAYED_HEADER] == "true"
    assert (seen["reused"], seen["keyless"]) == (
        "IDEMPOTENCY_KEY_REUSED",
        "IDEMPOTENCY_KEY_REQUIRED",
    )
    assert seen["bookings"] == 1


def test_what_a_hold_refuses(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        another = await _listing(ops, beds=1)
        student, other = await _student(ops), await _student(ops)
        refused: dict[str, Any] = {}

        def said(response: httpx.Response) -> tuple[int, str]:
            return response.status_code, response.json()["code"]

        quote = await _quote(student, _category_of(listing))
        ops.app.state.flags = FixedFlags(remote_booking_enabled=False)
        refused["visit first"] = said(await _hold(student, quote["id"]))
        ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
        refused["staff"] = (await _hold(ops, quote["id"])).status_code
        refused["someone else's quote"] = said(await _hold(other, quote["id"]))
        refused["no such quote"] = said(await _hold(student, str(uuid.uuid7())))
        # Asked for signed out: nobody's, so no one's to book.
        anonymous = await _anyone(ops.app, _quote_body(_category_of(listing)), ip="198.51.100.7")
        refused["a quote asked for signed out"] = said(await _hold(student, anonymous.json()["id"]))
        assert (await _hold(student, quote["id"])).status_code == 201
        refused["a second hold"] = said(
            await _hold(student, (await _quote(student, _category_of(another)))["id"])
        )
        refused["the bed is taken"] = said(
            await _hold(other, (await _quote(other, _category_of(listing)))["id"])
        )
        # Past the hold's 15 minutes but within the quote's 30: the student holds nothing
        # now, and the quote has made its booking.
        ops.app.state.clock.advance(timedelta(minutes=16))
        refused["the same quote again"] = said(await _hold(student, quote["id"]))
        ops.app.state.clock.advance(timedelta(minutes=15))
        refused["an expired quote"] = said(await _hold(student, quote["id"]))
        return refused

    assert run(scenario) == {
        "visit first": (409, "BOOKING_NEEDS_VISIT"),
        "staff": 403,
        "someone else's quote": (404, "NOT_FOUND"),
        "no such quote": (404, "NOT_FOUND"),
        "a quote asked for signed out": (404, "NOT_FOUND"),
        "a second hold": (409, "HOLD_LIMIT_REACHED"),
        "the bed is taken": (409, "BED_UNAVAILABLE"),
        "the same quote again": (409, "QUOTE_USED"),
        "an expired quote": (409, "QUOTE_EXPIRED"),
    }


def test_an_expired_hold_frees_its_bed_for_the_next_student(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        first, second = await _student(ops), await _student(ops)
        early = (await _hold(first, (await _quote(first, _category_of(listing)))["id"])).json()
        later_quote = await _quote(second, _category_of(listing))
        before = (await _hold(second, later_quote["id"])).status_code
        ops.app.state.clock.advance(timedelta(minutes=15))
        after = await _hold(second, later_quote["id"])
        expired = await _booking(ops, early["code"])
        async with ops.app.state.sessionmaker() as db:
            allocations = (
                await db.execute(
                    select(InventoryAllocation.booking_id, InventoryAllocation.is_active).where(
                        InventoryAllocation.booking_id.in_(
                            select(Booking.id).where(Booking.property_id == expired.property_id)
                        )
                    )
                )
            ).all()
            events = (
                await db.execute(
                    select(BookingEventRecord.event, BookingEventRecord.actor_type)
                    .where(BookingEventRecord.booking_id == expired.id)
                    .order_by(BookingEventRecord.id)
                )
            ).all()
        return {
            "before": before,
            "after": after.status_code,
            "expired": (expired.status, expired.version),
            "active": sorted(active for booking, active in allocations),
            "events": [tuple(event) for event in events],
            "mine": (await first.ok("GET", f"{HOLDS}/{early['code']}"))["status"],
        }

    assert run(scenario) == {
        "before": 409,
        # At exactly 15 minutes the hold has expired, and the second student takes the bed.
        "after": 201,
        "expired": ("expired", 2),
        "active": [False, True],
        "events": [("hold", "student"), ("hold_expired", "system")],
        "mine": "expired",
    }


def test_fifty_students_asking_at_once_hold_the_last_bed_once(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        # The owner's offline tenant has one bed, so one is left.
        bed = listing["categories"][0]["rooms"][0]["beds"][0]["id"]
        await ops.ok(
            "POST",
            f"/v1/ops/beds/{bed}/blocks",
            json={"kind": "offline_tenant", "start": "2027-08-01", "end": None},
        )
        students = [await _student(ops) for _ in range(50)]
        quotes = [await _quote(student, _category_of(listing)) for student in students]
        answers = await asyncio.gather(
            *(_hold(student, quote["id"]) for student, quote in zip(students, quotes, strict=True))
        )
        won = [answer.json()["code"] for answer in answers if answer.status_code == 201]
        winner = await _booking(ops, won[0])
        async with ops.app.state.sessionmaker() as db:
            held = await db.scalar(
                select(func.count()).where(
                    Booking.property_id == winner.property_id, Booking.status == "held"
                )
            )
            # Pairs of the PG's active allocations that share a bed and a day: none, ever.
            overlapping = await db.scalar(
                text(
                    "SELECT count(*) FROM inventory_allocations a JOIN inventory_allocations b"
                    " ON a.bed_id = b.bed_id AND a.id < b.id AND a.period && b.period"
                    " WHERE a.is_active AND b.is_active AND a.bed_id = ANY(:beds)"
                ),
                {"beds": list((await _beds(ops, listing)).values())},
            )
        return {
            "statuses": sorted(answer.status_code for answer in answers),
            "codes": {answer.json()["code"] for answer in answers if answer.status_code == 409},
            "held": held,
            "overlapping": overlapping,
        }

    seen = run(scenario)

    assert seen["statuses"] == [201] + [409] * 49
    assert seen["codes"] == {"BED_UNAVAILABLE"}
    assert seen["held"] == 1
    assert seen["overlapping"] == 0


def test_a_bookings_history_is_never_rewritten(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[bool]:
        listing = await _listing(ops, beds=1)
        student = await _student(ops)
        code = (await _hold(student, (await _quote(student, _category_of(listing)))["id"])).json()[
            "code"
        ]
        booking = await _booking(ops, code)
        refused = []
        for statement in (
            "UPDATE booking_events SET to_status = 'active' WHERE booking_id = :id",
            "DELETE FROM booking_events WHERE booking_id = :id",
        ):
            with pytest.raises(DBAPIError) as error:
                async with ops.app.state.sessionmaker() as db, db.begin():
                    await db.execute(text(statement), {"id": booking.id})
            refused.append("booking_events is append-only" in str(error.value))
        return refused

    assert run(scenario) == [True, True]


def test_a_code_another_booking_has_is_drawn_again(
    run: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario(ops: Staff) -> tuple[str, str]:
        listing = await _listing(ops, beds=2)
        first, second = await _student(ops), await _student(ops)
        taken = (await _hold(first, (await _quote(first, _category_of(listing)))["id"])).json()
        fresh = new_booking_code()
        draws = iter([taken["code"], fresh])
        monkeypatch.setattr(
            "app.modules.booking.service.holds.new_booking_code", lambda: next(draws)
        )
        quote = await _quote(second, _category_of(listing))
        return (await _hold(second, quote["id"])).json()["code"], fresh

    code, fresh = run(scenario)

    assert code == fresh
