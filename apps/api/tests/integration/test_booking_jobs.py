"""The booking jobs (step 5.8, ARCHITECTURE §7.5, ADR 0052): holds whose time is up end, and
confirmed bookings whose student never moved in end after the terms' wait, each at its exact
moment in India, through the state machine. Running a job twice changes nothing the second time,
and each counts what it moved."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.outbox import enqueue
from app.core.scheduler import DailyAt, Every
from app.jobs import SCHEDULES
from app.modules.booking.jobs import (
    CHECK_WINDOWS,
    CONFIRMATION_TIMEOUTS,
    EXPIRE_HOLDS,
    NO_SHOWS,
)
from app.modules.inventory.models import InventoryAllocation
from tests.flags import FixedFlags
from tests.integration.test_booking_check_in import _confirmed
from tests.integration.test_booking_confirmation import _about, _booking, _held, _history
from tests.integration.test_booking_holds import _listing
from tests.jobs import RecordedTexts, run_due_jobs
from tests.metrics import added, totals
from tests.staff_api import NOW, Staff, run_as_staff

pytestmark = pytest.mark.integration

# The move-in is 20 Aug 2027 and the terms wait 3 days: the student may still arrive on 23 Aug,
# and the booking ends on 24 Aug, at 10:00 in India.
LAST_DAY = datetime(2027, 8, 23, 4, 30, tzinfo=UTC)
NEXT_MORNING = datetime(2027, 8, 24, 4, 30, tzinfo=UTC)


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


async def _job(ops: Staff, kind: str, texts: RecordedTexts | None = None) -> None:
    """The scheduler's run of ``kind``, now."""
    async with ops.app.state.sessionmaker() as db, db.begin():
        await enqueue(db, kind, {}, clock=ops.app.state.clock)
    await run_due_jobs(ops.app, texts=texts)


async def _state(ops: Staff, code: str) -> tuple[str, int, bool]:
    """The booking's status and version, and whether its bed is still held for it."""
    booking = await _booking(ops, code)
    async with ops.app.state.sessionmaker() as db:
        held = await db.scalar(
            select(InventoryAllocation.is_active).where(
                InventoryAllocation.booking_id == booking.id
            )
        )
    return booking.status, booking.version, bool(held)


def test_a_hold_ends_when_its_time_is_up_and_a_second_run_changes_nothing(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        _, held = await _held(ops, await _listing(ops, beds=1))
        code = held["code"]
        moved = totals("booking.transitions")
        counted = totals("booking.job.changes")
        ops.app.state.clock.set(NOW + timedelta(minutes=15) - timedelta(seconds=1))
        await _job(ops, EXPIRE_HOLDS)
        seen: dict[str, Any] = {"a second before": await _state(ops, code)}
        ops.app.state.clock.advance(timedelta(seconds=1))
        await _job(ops, EXPIRE_HOLDS)
        seen["on the minute"] = await _state(ops, code)
        await _job(ops, EXPIRE_HOLDS)
        seen["run again"] = await _state(ops, code)
        seen["history"] = (await _history(ops, code))[-1]
        seen["transitions"] = added(
            moved,
            totals("booking.transitions"),
            event="hold_expired",
            **{"from": "held", "to": "expired", "by": "system"},
        )
        seen["counted"] = added(counted, totals("booking.job.changes"), job=EXPIRE_HOLDS)
        return seen

    seen = run(scenario)

    assert seen["a second before"] == ("held", 1, True)
    assert seen["on the minute"] == ("expired", 2, False)
    assert seen["run again"] == ("expired", 2, False)
    assert seen["history"] == ("hold_expired", "system")
    # Other tests' holds in the shared database may end in the same runs.
    assert seen["transitions"] >= 1
    assert seen["counted"] == seen["transitions"]


def test_a_student_who_never_moved_in_loses_the_booking_after_the_terms_wait(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        _, _, code = await _confirmed(ops)
        texts = RecordedTexts()
        ops.app.state.clock.set(LAST_DAY)
        await _job(ops, NO_SHOWS, texts)
        seen: dict[str, Any] = {"on the last day": await _state(ops, code)}
        ops.app.state.clock.set(NEXT_MORNING)
        await _job(ops, NO_SHOWS, texts)
        seen["the next morning"] = await _state(ops, code)
        await _job(ops, NO_SHOWS, texts)
        seen["run again"] = await _state(ops, code)
        booking = await _booking(ops, code)
        seen["ended"] = (booking.cancelled_at, booking.cancelled_by, booking.cancellation_kind)
        seen["history"] = (await _history(ops, code))[-1]
        seen["texts"] = sorted(_about(texts, code))
        return seen

    seen = run(scenario)

    assert seen["on the last day"] == ("confirmed", 3, True)
    assert seen["the next morning"] == ("no_show", 4, False)
    assert seen["run again"] == ("no_show", 4, False)
    assert seen["ended"] == (NEXT_MORNING, "system", "no_show")
    assert seen["history"] == ("no_show", "system")
    assert [template for template, _ in seen["texts"]] == [
        "booking_no_show_for_owner",
        "booking_no_show_refunded",
    ]
    assert {values["last_day"] for _, values in seen["texts"]} == {"23 Aug 2027"}


def test_a_no_show_text_says_so_when_the_terms_keep_the_token(
    run: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Refunding in full is the only late rule a policy may take until payments go through
    # Razorpay Route (PRODUCT_CONTEXT §9); the text for a kept token is ready for the day it may.
    monkeypatch.setattr("app.modules.booking.service.notices.late_refund", lambda *_: 0)

    async def scenario(ops: Staff) -> list[str]:
        _, _, code = await _confirmed(ops)
        texts = RecordedTexts()
        ops.app.state.clock.set(NEXT_MORNING)
        await _job(ops, NO_SHOWS, texts)
        return sorted(template for template, _ in _about(texts, code))

    assert run(scenario) == ["booking_no_show_for_owner", "booking_no_show_kept"]


def test_every_booking_job_runs_as_section_7_5_says() -> None:
    schedules = {job.kind: job.schedule for job in SCHEDULES}

    assert schedules[EXPIRE_HOLDS] == Every(timedelta(minutes=1))
    assert schedules[CONFIRMATION_TIMEOUTS] == Every(timedelta(minutes=5))
    assert schedules[CHECK_WINDOWS] == Every(timedelta(minutes=5))
    assert schedules[NO_SHOWS] == DailyAt(time(10, 0))
