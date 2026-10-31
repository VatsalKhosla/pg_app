"""Moving in, in the API (step 5.6, ADR 0050): the student says they've moved in from the day
before the move-in, their 24 hours to check the room start then, and the booking settles once
they're over; ops can ask a student who has moved in to say so. All at India's time."""

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
from tests.flags import FixedFlags
from tests.integration.test_booking_confirmation import (
    _about,
    _booking,
    _held,
    _history,
    _owner_of,
    _secure,
)
from tests.integration.test_booking_holds import _listing, _student
from tests.integration.test_booking_student import _again
from tests.jobs import RecordedTexts, run_due_jobs
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration

BOOKINGS = "/v1/bookings"
# The move-in is 20 Aug 2027, so checking in opens at midnight on 19 Aug in India.
OPENS = datetime(2027, 8, 18, 18, 30, tzinfo=UTC)
# 11:30 am in India on the move-in day.
MOVED_IN = datetime(2027, 8, 20, 6, 0, tzinfo=UTC)


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


async def _confirmed(ops: Staff) -> tuple[Staff, Staff, str]:
    """A student, the owner, and the student's booking, which the owner has confirmed; its texts
    so far sent, as the worker sends them within seconds."""
    listing = await _listing(ops, beds=1)
    owner = await _owner_of(ops, listing)
    student, held = await _held(ops, listing)
    code: str = held["code"]
    await _secure(ops, code)
    await owner.ok("POST", f"/v1/owner/bookings/{code}/confirm")
    await run_due_jobs(ops.app)
    return student, owner, code


def _moving_in(booking: dict[str, Any]) -> tuple[str, str | None, bool, str | None]:
    assert booking["checkWindowHours"] == 24
    return (
        booking["status"],
        booking["checkInOpensOn"],
        booking["canCheckIn"],
        booking["checkWindowEndsAt"],
    )


def _refusal(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["code"]


def test_a_student_says_theyve_moved_in_from_the_day_before_the_move_in(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, owner, code = await _confirmed(ops)
        mine = f"{BOOKINGS}/{code}"
        seen: dict[str, Any] = {"confirmed": _moving_in(await student.ok("GET", mine))}
        ops.app.state.clock.set(OPENS - timedelta(seconds=1))
        student = await _again(student)
        seen["a second early"] = _moving_in(await student.ok("GET", mine))
        early = await student.call("POST", f"{mine}/check-in")
        seen["refused"] = (*_refusal(early), early.json()["detail"])
        ops.app.state.clock.advance(timedelta(seconds=1))
        seen["open"] = _moving_in(await student.ok("GET", mine))
        someone_else = await _student(ops)
        seen["someone else"] = (await someone_else.call("POST", f"{mine}/check-in")).status_code
        seen["checked in"] = _moving_in(await student.ok("POST", f"{mine}/check-in"))
        seen["again"] = _refusal(await student.call("POST", f"{mine}/check-in"))
        owner = await _again(owner)
        managed = await owner.ok("GET", f"/v1/owner/bookings/{code}")
        seen["owner sees"] = (managed["checkedInAt"], managed["checkWindowEndsAt"])
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        seen["texts"] = dict(_about(texts, code))
        seen["history"] = await _history(ops, code)
        seen["checked in at"] = (await _booking(ops, code)).checked_in_at
        return seen

    seen = run(scenario)

    assert seen["confirmed"] == ("confirmed", "2027-08-19", False, None)
    assert seen["a second early"] == ("confirmed", "2027-08-19", False, None)
    assert seen["refused"] == (
        409,
        "INVALID_TRANSITION",
        "Checking in opens the day before the move-in.",
    )
    assert seen["open"] == ("confirmed", "2027-08-19", True, None)
    assert seen["someone else"] == 404
    # Their 24 hours start as they say so.
    assert seen["checked in"] == ("checked_in", None, False, "2027-08-19T18:30:00Z")
    assert seen["again"] == (409, "INVALID_TRANSITION")
    assert seen["owner sees"] == ("2027-08-18T18:30:00Z", "2027-08-19T18:30:00Z")
    assert seen["checked in at"] == OPENS
    assert seen["history"][-1] == ("check_in", "student")
    assert list(seen["texts"]) == ["booking_moved_in"]
    assert seen["texts"]["booking_moved_in"]["window_ends"] == "Fri 20 Aug, 12:00 am"


def test_the_booking_settles_when_the_24_hours_are_over_and_not_before(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, _, code = await _confirmed(ops)
        ops.app.state.clock.set(MOVED_IN)
        student = await _again(student)
        await student.ok("POST", f"{BOOKINGS}/{code}/check-in")
        texts = RecordedTexts()

        async def check_windows() -> tuple[str, int]:
            async with ops.app.state.sessionmaker() as db, db.begin():
                await enqueue(db, CHECK_WINDOWS, {}, clock=ops.app.state.clock)
            await run_due_jobs(ops.app, texts=texts)
            booking = await _booking(ops, code)
            return booking.status, booking.version

        ops.app.state.clock.advance(timedelta(hours=24) - timedelta(seconds=1))
        seen: dict[str, Any] = {"a second before": await check_windows()}
        ops.app.state.clock.advance(timedelta(seconds=1))
        seen["at 24 hours"] = await check_windows()
        # A second run finds nothing left to do.
        seen["run again"] = await check_windows()
        seen["activated at"] = (await _booking(ops, code)).activated_at
        seen["history"] = await _history(ops, code)
        seen["texts"] = sorted(template for template, _ in _about(texts, code))
        student = await _again(student)
        seen["student sees"] = (await student.ok("GET", f"{BOOKINGS}/{code}"))["status"]
        return seen

    seen = run(scenario)

    assert seen["a second before"] == ("checked_in", 4)
    assert seen["at 24 hours"] == ("active", 5)
    assert seen["run again"] == ("active", 5)
    assert seen["activated at"] == MOVED_IN + timedelta(hours=24)
    assert seen["history"][-2:] == [("check_in", "student"), ("window_elapsed", "system")]
    assert seen["texts"] == ["booking_moved_in", "booking_settled", "booking_settled_for_owner"]
    assert seen["student sees"] == "active"


def test_ops_ask_a_student_whos_moved_in_to_say_so_once_a_day_at_most(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, _, code = await _confirmed(ops)
        reminder = f"/v1/ops/bookings/{code}/move-in-reminder"
        seen: dict[str, Any] = {"too soon": _refusal(await ops.call("POST", reminder))}
        ops.app.state.clock.set(MOVED_IN)
        ops = await _again(ops, kind=SessionKind.STAFF)
        seen["asked"] = await ops.ok("POST", reminder)
        seen["asked again"] = await ops.ok("POST", reminder)
        ops.app.state.clock.advance(timedelta(days=1))
        ops = await _again(ops, kind=SessionKind.STAFF)
        seen["next day"] = await ops.ok("POST", reminder)
        booking = await _booking(ops, code)
        seen["booking"] = (booking.status, booking.version)
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        seen["texts"] = [
            values["hours"]
            for template, values in _about(texts, code)
            if template == "booking_confirm_move_in"
        ]
        student = await _again(student)
        await student.ok("POST", f"{BOOKINGS}/{code}/check-in")
        seen["once moved in"] = _refusal(await ops.call("POST", reminder))
        async with ops.app.state.sessionmaker() as db:
            seen["audit"] = list(
                await db.scalars(
                    select(AuditLog.details)
                    .where(
                        AuditLog.entity_id == code,
                        AuditLog.action == "booking.move_in_reminder",
                    )
                    .order_by(AuditLog.id)
                )
            )
        return seen

    seen = run(scenario)

    assert seen["too soon"] == (409, "INVALID_TRANSITION")
    assert (seen["asked"], seen["asked again"], seen["next day"]) == (
        {"sent": True},
        {"sent": False},
        {"sent": True},
    )
    # Nothing changes until the student says so themselves.
    assert seen["booking"] == ("confirmed", 3)
    assert seen["texts"] == ["24", "24"]
    assert seen["once moved in"] == (409, "INVALID_TRANSITION")
    assert seen["audit"] == [{"sent": True}, {"sent": False}, {"sent": True}]
