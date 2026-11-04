"""The bookings board's timers and actions, without a database (step 5.10, ADR 0054): what a
booking is waiting for, when that's late, what needs a person now, and what ops may do, each at
its edge in India."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.money import rupees
from app.modules.booking.domain.board import (
    BoardTimer,
    OpsAction,
    TimerKind,
    needs_attention,
    ops_actions,
    timer_of,
)
from app.modules.booking.domain.state_machine import BookingFacts, BookingStatus, Moment
from app.modules.pricing.domain.policies import BookingPolicy, LateCancelPolicy

S = BookingStatus
TERMS = BookingPolicy(
    token_paise=rupees(2_000),
    hold_minutes=15,
    free_cancel_days=7,
    check_window_hours=24,
    confirm_deadline_hours=12,
    no_show_days=3,
    late_cancel_policy=LateCancelPolicy.REFUND_FULL,
    max_active_holds_per_user=1,
    max_advance_days=120,
)
MOVE_IN = date(2027, 8, 20)
# 11:30 am in India, on the move-in day.
NOW = datetime(2027, 8, 20, 6, 0, tzinfo=UTC)
# Midnight in India, at the start of the move-in day and of the next.
MOVE_IN_STARTS = datetime(2027, 8, 19, 18, 30, tzinfo=UTC)
NEXT_DAY_STARTS = datetime(2027, 8, 20, 18, 30, tzinfo=UTC)


def _timer(status: BookingStatus, now: datetime = NOW) -> BoardTimer | None:
    return timer_of(status, token_secured_at=NOW, disputed_at=NOW, move_in=MOVE_IN, now=now)


def _facts(status: BookingStatus) -> BookingFacts:
    return BookingFacts(
        status=status,
        move_in=MOVE_IN,
        token_paise=rupees(2_000),
        instant_confirm=False,
    )


def test_a_token_waits_two_hours_for_its_owner_then_ops_step_in() -> None:
    timer = _timer(S.TOKEN_SECURED)

    assert timer == BoardTimer(TimerKind.UNCONFIRMED, NOW, NOW + timedelta(hours=2))
    a_second_before = NOW + timedelta(hours=2) - timedelta(seconds=1)
    assert not timer.late(a_second_before)
    assert not needs_attention(timer, a_second_before)
    assert timer.late(timer.due)
    assert needs_attention(timer, timer.due)


def test_a_dispute_is_due_by_the_end_of_its_day_in_india_and_always_needs_a_person() -> None:
    timer = _timer(S.DISPUTED)

    assert timer == BoardTimer(TimerKind.DISPUTE, NOW, NEXT_DAY_STARTS)
    assert needs_attention(timer, NOW)
    assert not timer.late(NEXT_DAY_STARTS - timedelta(seconds=1))
    assert timer.late(NEXT_DAY_STARTS)


def test_a_dispute_reported_after_midnight_utc_is_due_by_the_end_of_indias_day() -> None:
    # 5:29 am on the 21st in UTC is 10:59 am on the 21st in India; 6 pm on the 20th in UTC is
    # 11:30 pm on the 20th in India.
    late_evening = datetime(2027, 8, 20, 18, 0, tzinfo=UTC)

    found = timer_of(
        S.DISPUTED, token_secured_at=None, disputed_at=late_evening, move_in=MOVE_IN, now=NOW
    )

    assert found is not None
    assert found.due == NEXT_DAY_STARTS


def test_a_move_in_is_due_from_the_start_of_its_day_and_late_from_the_next() -> None:
    assert _timer(S.CONFIRMED, MOVE_IN_STARTS - timedelta(seconds=1)) is None
    due = _timer(S.CONFIRMED, MOVE_IN_STARTS)
    assert due == BoardTimer(TimerKind.MOVE_IN, MOVE_IN_STARTS, NEXT_DAY_STARTS)
    assert needs_attention(due, MOVE_IN_STARTS)
    assert not due.late(NEXT_DAY_STARTS - timedelta(seconds=1))
    assert due.late(NEXT_DAY_STARTS)


@pytest.mark.parametrize(
    "status",
    [
        S.HELD,
        S.CHECKED_IN,
        S.ACTIVE,
        S.COMPLETED,
        S.EXPIRED,
        S.CANCELLED,
        S.REJECTED,
        S.NO_SHOW,
        S.REFUNDED,
    ],
)
def test_nothing_else_is_on_a_clock(status: BookingStatus) -> None:
    timer = _timer(status)

    assert timer is None
    assert not needs_attention(timer, NOW)


@pytest.mark.parametrize("status", [S.TOKEN_SECURED, S.DISPUTED])
def test_a_booking_without_its_stamp_is_on_no_clock(status: BookingStatus) -> None:
    assert (
        timer_of(status, token_secured_at=None, disputed_at=None, move_in=MOVE_IN, now=NOW) is None
    )


@pytest.mark.parametrize(
    ("status", "now", "expected"),
    [
        (S.HELD, NOW, []),
        (S.TOKEN_SECURED, NOW, [OpsAction.CONFIRM, OpsAction.REJECT, OpsAction.OWNER_CANCEL]),
        # Three weeks before the move-in: too soon to ask whether they've moved in.
        (S.CONFIRMED, NOW - timedelta(days=21), [OpsAction.OWNER_CANCEL]),
        (S.CONFIRMED, NOW, [OpsAction.OWNER_CANCEL, OpsAction.REMIND_MOVE_IN]),
        (S.CHECKED_IN, NOW, []),
        (S.DISPUTED, NOW, []),
        # A move-out comes after the move-in, so not on that day itself.
        (S.ACTIVE, NOW, []),
        (S.ACTIVE, NOW + timedelta(days=1), [OpsAction.MOVE_OUT]),
        (S.COMPLETED, NOW, []),
        (S.CANCELLED, NOW, []),
    ],
)
def test_ops_are_offered_what_the_state_machine_would_take(
    status: BookingStatus, now: datetime, expected: list[OpsAction]
) -> None:
    facts = _facts(status)
    if status is S.TOKEN_SECURED:
        facts = replace(facts, confirm_by=now + timedelta(hours=12))

    assert ops_actions(facts, Moment(now), TERMS) == expected
