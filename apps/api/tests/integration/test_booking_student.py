"""A student's bookings in the API (step 5.5, ADR 0049): their list, each booking's history and
what cancelling it now gives back, the owner's contact once it's confirmed (rule 11), and
cancelling, for free until the cutoff and as the late-cancel rule says after it (rule 9)."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.service import SessionService
from app.modules.inventory.models import InventoryAllocation
from tests.flags import FixedFlags
from tests.integration.test_booking_confirmation import _booking, _held, _owner_of, _secure
from tests.integration.test_booking_holds import _category_of, _hold, _listing, _quote, _student
from tests.jobs import RecordedTexts, run_due_jobs
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration

BOOKINGS = "/v1/bookings"


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


async def _again(student: Staff) -> Staff:
    """The same student signed in again, once the clock has moved past their session."""
    async with student.app.state.sessionmaker() as db:
        session = await SessionService(db, student.app.state.clock).start(
            student.user_id, kind=SessionKind.USER, ip_address=None, user_agent=None
        )
    return Staff(student.app, student.client, user_id=student.user_id, token=session.token)


def _steps(booking: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(step["event"], step["status"], step["by"]) for step in booking["timeline"]]


def test_a_student_sees_their_bookings_and_the_address_once_confirmed(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        owner = await _owner_of(ops, listing)
        student, held = await _held(ops, listing)
        code, slug = held["code"], held["property"]["slug"]
        contact = f"/v1/properties/{slug}/contact"
        seen: dict[str, Any] = {"held": held}
        seen["hidden"] = (await student.call("GET", contact)).json()["code"]
        await _secure(ops, code)
        await owner.ok("POST", f"/v1/owner/bookings/{code}/confirm")
        seen["confirmed"] = await student.ok("GET", f"{BOOKINGS}/{code}")
        seen["contact"] = await student.ok("GET", contact)
        seen["list"] = await student.ok("GET", BOOKINGS)
        return seen

    seen = run(scenario)

    held = seen["held"]
    assert _steps(held) == [("hold", "held", "student")]
    # Nothing's been paid yet, so nothing comes back.
    assert held["cancellation"] == {"refundPaise": 0, "late": False}
    assert seen["hidden"] == "CONTACT_HIDDEN"
    confirmed = seen["confirmed"]
    assert _steps(confirmed) == [
        ("hold", "held", "student"),
        ("token_secured", "token_secured", "system"),
        ("confirm", "confirmed", "owner"),
    ]
    assert confirmed["cancellation"] == {"refundPaise": confirmed["tokenPaise"], "late": False}
    assert seen["contact"]["addressLine"] == "House 1, a fictional lane"
    assert [item["code"] for item in seen["list"]["items"]] == [held["code"]]


def test_a_student_cancels_for_free_and_the_owner_hears(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        owner = await _owner_of(ops, listing)
        student, held = await _held(ops, listing)
        code = held["code"]
        await _secure(ops, code)
        await owner.ok("POST", f"/v1/owner/bookings/{code}/confirm")
        token = held["tokenPaise"]
        cancelled = await student.ok(
            "POST", f"{BOOKINGS}/{code}/cancel", json={"refundPaise": token}
        )
        again = await student.call("POST", f"{BOOKINGS}/{code}/cancel", json={"refundPaise": 0})
        booking = await _booking(ops, code)
        async with ops.app.state.sessionmaker() as db:
            active = await db.scalar(
                select(InventoryAllocation.is_active).where(
                    InventoryAllocation.booking_id == booking.id
                )
            )
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        return {
            "status": cancelled["status"],
            "cancellation": cancelled["cancellation"],
            "ended": (booking.cancelled_by, booking.cancellation_kind),
            "again": again.json()["code"],
            "active": active,
            "owner heard": [
                template for _, template, values in texts.sent if values.get("code") == code
            ][-1],
        }

    assert run(scenario) == {
        "status": "cancelled",
        "cancellation": None,
        "ended": ("student", "cancel"),
        "again": "INVALID_TRANSITION",
        "active": False,
        "owner heard": "booking_cancelled_by_student",
    }


def test_past_the_cutoff_a_cancellation_is_late(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        owner = await _owner_of(ops, listing)
        student, held = await _held(ops, listing)
        code = held["code"]
        await _secure(ops, code)
        await owner.ok("POST", f"/v1/owner/bookings/{code}/confirm")
        # The move-in is 20 Aug 2027; free cancellation ends on 13 Aug in India.
        ops.app.state.clock.set(datetime(2027, 8, 13, 18, 30, tzinfo=UTC))
        student = await _again(student)
        looked = await student.ok("GET", f"{BOOKINGS}/{code}")
        cancelled = await student.ok(
            "POST",
            f"{BOOKINGS}/{code}/cancel",
            json={"refundPaise": looked["cancellation"]["refundPaise"]},
        )
        booking = await _booking(ops, code)
        return {
            "looked": looked["cancellation"],
            "token": held["tokenPaise"],
            "status": cancelled["status"],
            "kind": booking.cancellation_kind,
        }

    seen = run(scenario)

    # Refund in full is the late-cancel rule until Razorpay Route (PRODUCT_CONTEXT §9).
    assert seen["looked"] == {"refundPaise": seen["token"], "late": True}
    assert (seen["status"], seen["kind"]) == ("cancelled", "cancel_late")


def test_a_cancellation_refuses_a_refund_that_changed_and_other_students(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        student, held = await _held(ops, listing)
        code = held["code"]
        stranger = await _student(ops)
        seen = {
            "a stranger": (
                await stranger.call("POST", f"{BOOKINGS}/{code}/cancel", json={"refundPaise": 0})
            ).status_code,
        }
        # The student looked while it was a hold (nothing back), then the token came in.
        await _secure(ops, code)
        changed = await student.call("POST", f"{BOOKINGS}/{code}/cancel", json={"refundPaise": 0})
        seen["changed"] = changed.json()["code"]
        seen["still"] = (await student.ok("GET", f"{BOOKINGS}/{code}"))["status"]
        # A hold is cancelled for nothing back.
        other, other_held = await _held(ops, await _listing(ops, beds=1))
        seen["a hold"] = (
            await other.ok(
                "POST", f"{BOOKINGS}/{other_held['code']}/cancel", json={"refundPaise": 0}
            )
        )["status"]
        return seen

    assert run(scenario) == {
        "a stranger": 404,
        "changed": "REFUND_CHANGED",
        "still": "token_secured",
        "a hold": "cancelled",
    }


def test_staff_sessions_have_no_bookings_of_their_own(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> int:
        return (await ops.call("GET", BOOKINGS)).status_code

    assert run(scenario) == 403


def test_a_booking_list_is_newest_first(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[str]:
        first_listing, second_listing = await _listing(ops, beds=1), await _listing(ops, beds=1)
        student = await _student(ops)
        made = []
        for listing in (first_listing, second_listing):
            held = (
                await _hold(student, (await _quote(student, _category_of(listing)))["id"])
            ).json()
            made.append(held["code"])
            # Holds last 15 minutes and a student holds one at a time: cancel to hold the next.
            await student.ok("POST", f"{BOOKINGS}/{held['code']}/cancel", json={"refundPaise": 0})
            ops.app.state.clock.advance(timedelta(seconds=1))
        listed = await student.ok("GET", BOOKINGS)
        return [item["code"] for item in listed["items"]] + made

    codes = run(scenario)

    listed, made = codes[:2], codes[2:]
    assert listed == list(reversed(made))
