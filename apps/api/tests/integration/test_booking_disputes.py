"""Disputes in the API (step 5.7, ADR 0051): a student who has moved in reports, inside their
time to check the room, that it isn't as shown, with their own photos; ops find it in their queue
and settle it. A refund releases the bed, refunds the token and offers PGs like it; upholding it
lets the stay go ahead. Both text the student and the owner, and both are on the record."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.audit import AuditLog
from app.core.outbox import enqueue
from app.modules.booking.jobs import CHECK_WINDOWS
from app.modules.identity.domain.sessions import SessionKind
from app.modules.inventory.models import InventoryAllocation
from app.modules.media.domain.assets import AssetStatus, Purpose
from tests.flags import FixedFlags
from tests.integration.test_booking_check_in import MOVED_IN, _confirmed
from tests.integration.test_booking_confirmation import _about, _booking, _history
from tests.integration.test_booking_holds import _student
from tests.integration.test_booking_student import _again
from tests.jobs import RecordedTexts, run_due_jobs
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration

BOOKINGS = "/v1/bookings"
DISPUTES = "/v1/ops/disputes"
REPORT = {
    "reason": "not_as_shown",
    "description": "The listing showed a window; the room has none, and the bed is broken.",
}


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def remote_booking(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            return await scenario(ops)

        return run_as_staff(settings, remote_booking)

    return run_scenario


async def _moved_in(ops: Staff) -> tuple[Staff, Staff, str]:
    """Ops, signed in again once the clock has moved past their session; a student who has moved
    in at 11:30 am on the move-in day; and the booking."""
    student, _, code = await _confirmed(ops)
    ops.app.state.clock.set(MOVED_IN)
    student = await _again(student)
    await student.ok("POST", f"{BOOKINGS}/{code}/check-in")
    await run_due_jobs(ops.app)
    return await _again(ops, kind=SessionKind.STAFF), student, code


async def _photos(student: Staff, count: int) -> list[str]:
    return [await student.media(purpose=Purpose.DISPUTE_PHOTO) for _ in range(count)]


async def _queued(ops: Staff, code: str) -> dict[str, Any]:
    """The dispute about this booking in ops' open queue: the shared database holds others."""
    found: dict[str, Any] | None = None
    cursor: str | None = None
    while found is None:
        page = await ops.ok(
            "GET", DISPUTES, params={"status": "open", **({"cursor": cursor} if cursor else {})}
        )
        found = next((item for item in page["items"] if item["booking"] == code), None)
        cursor = page["nextCursor"]
        assert found is not None or cursor is not None, "not in the queue"
    return found


async def _bed_held(ops: Staff, code: str) -> bool:
    booking = await _booking(ops, code)
    async with ops.app.state.sessionmaker() as db:
        active = await db.scalar(
            select(InventoryAllocation.is_active).where(
                InventoryAllocation.booking_id == booking.id
            )
        )
    return bool(active)


def test_a_report_a_room_isnt_as_shown_refunded_by_ops_frees_the_bed(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        ops, student, code = await _moved_in(ops)
        mine = f"{BOOKINGS}/{code}"
        seen: dict[str, Any] = {"may report": (await student.ok("GET", mine))["canDispute"]}
        photos = await _photos(student, 2)
        reported = await student.ok("POST", f"{mine}/disputes", json={**REPORT, "photos": photos})
        seen["reported"] = (reported["status"], reported["dispute"], reported["canDispute"])
        seen["again"] = (await student.call("POST", f"{mine}/disputes", json=REPORT)).json()["code"]
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        queued = await _queued(ops, code)
        seen["queued"] = (queued["reason"], queued["photos"], queued["property"]["name"])
        found = await ops.ok("GET", f"{DISPUTES}/{queued['id']}")
        seen["ops see"] = (
            found["status"],
            found["description"],
            found["booking"]["status"],
            found["student"]["phone"].startswith("+91"),
            [photo["id"] for photo in found["photos"]],
            found["photos"][0]["sizes"][0]["url"],
        )
        resolved = await ops.ok(
            "POST",
            f"{DISPUTES}/{queued['id']}/resolve",
            json={"outcome": "refund", "notes": "Called the owner: the room was swapped."},
        )
        seen["resolved"] = (resolved["status"], resolved["notes"], resolved["resolvedAt"])
        seen["twice"] = (
            await ops.call(
                "POST",
                f"{DISPUTES}/{queued['id']}/resolve",
                json={"outcome": "uphold", "notes": "Second thoughts"},
            )
        ).json()["code"]
        await run_due_jobs(ops.app, texts=texts)
        seen["texts"] = sorted(template for template, _ in _about(texts, code))
        seen["bed held"] = await _bed_held(ops, code)
        seen["history"] = (await _history(ops, code))[-2:]
        after = await student.ok("GET", mine)
        seen["student sees"] = (after["status"], after["dispute"]["status"], after["rebook"])
        seen["rent"] = after["monthlyRentPaise"]
        seen["photos"] = photos
        async with ops.app.state.sessionmaker() as db:
            seen["audit"] = await db.scalar(
                select(AuditLog.details["note"].astext).where(
                    AuditLog.entity_id == code, AuditLog.action == "booking.resolve_refund"
                )
            )
        return seen

    seen = run(scenario)

    assert seen["may report"] is True
    status, dispute, may_report = seen["reported"]
    assert (status, may_report) == ("disputed", False)
    assert (dispute["reason"], dispute["status"], dispute["resolvedAt"]) == (
        "not_as_shown",
        "open",
        None,
    )
    assert seen["again"] == "INVALID_TRANSITION"
    assert seen["queued"][:2] == ("not_as_shown", 2)
    status, description, booking_status, has_phone, photo_ids, url = seen["ops see"]
    assert (status, description, booking_status, has_phone) == (
        "open",
        REPORT["description"],
        "disputed",
        True,
    )
    # In the student's order, behind links signed for five minutes.
    assert photo_ids == seen["photos"]
    assert "X-Amz-Expires=300" in url
    status, notes, resolved_at = seen["resolved"]
    assert (status, notes) == ("resolved_refund", "Called the owner: the room was swapped.")
    assert resolved_at == "2027-08-20T06:00:00Z"
    assert seen["twice"] == "INVALID_TRANSITION"
    assert seen["texts"] == [
        "booking_dispute_refunded",
        "booking_dispute_refunded_for_owner",
        "booking_disputed_for_owner",
    ]
    assert seen["bed held"] is False
    assert seen["history"] == [("dispute", "student"), ("resolve_refund", "ops")]
    status, dispute_status, rebook = seen["student sees"]
    assert (status, dispute_status) == ("refunded", "resolved_refund")
    # PGs like it, for the same month, up to a fifth above its rent.
    assert rebook == {
        "locality": "satya-niketan",
        "occupancy": "double",
        "gender": rebook["gender"],
        "moveInMonth": "2027-08",
        "budgetMaxPaise": seen["rent"] * 6 // 5,
    }
    assert seen["audit"] == "Called the owner: the room was swapped."


def test_an_upheld_report_lets_the_stay_go_ahead(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        ops, student, code = await _moved_in(ops)
        await student.ok("POST", f"{BOOKINGS}/{code}/disputes", json=REPORT)
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        queued = await _queued(ops, code)
        resolved = await ops.ok(
            "POST",
            f"{DISPUTES}/{queued['id']}/resolve",
            json={"outcome": "uphold", "notes": "Photos match the listing."},
        )
        # The settling job, once the 24 hours are over, finds nothing to do.
        ops.app.state.clock.advance(timedelta(days=1))
        async with ops.app.state.sessionmaker() as db, db.begin():
            await enqueue(db, CHECK_WINDOWS, {}, clock=ops.app.state.clock)
        await run_due_jobs(ops.app, texts=texts)
        booking = await _booking(ops, code)
        student = await _again(student)
        after = await student.ok("GET", f"{BOOKINGS}/{code}")
        return {
            "resolved": resolved["status"],
            "booking": (booking.status, booking.activated_at),
            "bed held": await _bed_held(ops, code),
            "texts": sorted(template for template, _ in _about(texts, code)),
            "history": (await _history(ops, code))[-2:],
            "student sees": (after["status"], after["dispute"]["status"], after["rebook"]),
        }

    assert run(scenario) == {
        "resolved": "resolved_uphold",
        "booking": ("active", MOVED_IN),
        "bed held": True,
        "texts": [
            "booking_dispute_upheld",
            "booking_dispute_upheld_for_owner",
            "booking_disputed_for_owner",
        ],
        "history": [("dispute", "student"), ("resolve_uphold", "ops")],
        "student sees": ("active", "resolved_uphold", None),
    }


def test_a_report_comes_inside_the_check_window_with_the_students_own_ready_photos(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, _, code = await _confirmed(ops)
        report = f"{BOOKINGS}/{code}/disputes"
        seen: dict[str, Any] = {
            "before moving in": (await student.call("POST", report, json=REPORT)).json()["code"]
        }
        ops.app.state.clock.set(MOVED_IN)
        student = await _again(student)
        await student.ok("POST", f"{BOOKINGS}/{code}/check-in")
        other = await _student(ops)
        refused = [
            await other.media(purpose=Purpose.DISPUTE_PHOTO),
            await student.media(AssetStatus.PROCESSING, purpose=Purpose.DISPUTE_PHOTO),
            await student.media(purpose=Purpose.VERIFICATION_PHOTO),
        ]
        bad = await student.call("POST", report, json={**REPORT, "photos": refused})
        seen["bad photos"] = (bad.status_code, bad.json()["code"], bad.json()["detail"])
        seen["too many"] = (
            await student.call("POST", report, json={**REPORT, "photos": await _photos(student, 7)})
        ).status_code
        seen["someone else"] = (await other.call("POST", report, json=REPORT)).status_code
        # Their 24 hours end at 11:30 am the next day: a report at that moment is too late.
        ops.app.state.clock.set(MOVED_IN + timedelta(hours=24))
        student = await _again(student)
        seen["can at the end"] = (await student.ok("GET", f"{BOOKINGS}/{code}"))["canDispute"]
        late = await student.call("POST", report, json=REPORT)
        seen["at the end"] = (late.status_code, late.json()["detail"])
        ops.app.state.clock.set(MOVED_IN + timedelta(hours=24) - timedelta(seconds=1))
        student = await _again(student)
        seen["a second before"] = (await student.ok("POST", report, json=REPORT))["status"]
        return seen

    seen = run(scenario)

    assert seen["before moving in"] == "INVALID_TRANSITION"
    status, code, detail = seen["bad photos"]
    assert (status, code) == (422, "DISPUTE_INVALID")
    assert "no such photo" in detail
    assert "is processing" in detail
    assert "isn't a photo for a report" in detail
    assert seen["too many"] == 422
    assert seen["someone else"] == 404
    assert seen["can at the end"] is False
    assert seen["at the end"] == (
        409,
        "The time to report a problem with the room has passed.",
    )
    assert seen["a second before"] == "disputed"


def test_a_student_uploads_photos_for_a_report_and_nothing_else(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> tuple[int, int, int]:
        student = await _student(ops)

        async def start(purpose: str) -> int:
            body = {"purpose": purpose, "contentType": "image/jpeg", "byteSize": 1_000}
            return (await student.call("POST", "/v1/media", json=body)).status_code

        listing = await start("listing_photo")
        uploads = [await start("dispute_photo") for _ in range(19)]
        assert set(uploads) == {201}
        return listing, uploads[0], await start("dispute_photo")

    # 20 tries an hour, refused ones too, then 429 until the hour is up.
    assert run(scenario) == (403, 201, 429)


def test_ops_queue_is_oldest_first_and_pages(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[str]:
        codes = []
        for _ in range(3):
            ops, student, code = await _moved_in(ops)
            await student.ok("POST", f"{BOOKINGS}/{code}/disputes", json=REPORT)
            ops.app.state.clock.set(datetime(2027, 7, 14, 10, 0, tzinfo=UTC))
            codes.append(code)
        seen: list[str] = []
        cursor: str | None = None
        while True:
            page = await ops.ok(
                "GET", DISPUTES, params={"limit": 2, **({"cursor": cursor} if cursor else {})}
            )
            seen.extend(item["booking"] for item in page["items"] if item["booking"] in codes)
            cursor = page["nextCursor"]
            if cursor is None:
                break
        return [code for code in seen if code in codes] + codes

    found = run(scenario)

    assert found[:3] == found[3:]
