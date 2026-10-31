"""What cancelling a booking now would mean for the student (step 5.5, ADR 0049): nothing back
before the token is in, the whole token until the free-cancellation cutoff, and the late-cancel
rule's share after it, as India's day turns."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.money import rupees
from app.modules.booking.domain.cancellation import Cancellation, cancellation, late_refund
from app.modules.booking.domain.state_machine import (
    BookingEvent,
    BookingFacts,
    BookingStatus,
    Moment,
)
from app.modules.pricing.domain.policies import BookingPolicy, LateCancelPolicy

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
MOVE_IN = date(2027, 7, 14)
TOKEN = rupees(2_000)


def _india(day: date, hour: int, minute: int = 0) -> Moment:
    moment = datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)
    return Moment(moment - timedelta(hours=5, minutes=30))


def _booking(status: BookingStatus) -> BookingFacts:
    return BookingFacts(status=status, move_in=MOVE_IN, token_paise=TOKEN, instant_confirm=False)


EARLY = _india(MOVE_IN - timedelta(days=20), 10)
LAST_FREE = _india(MOVE_IN - timedelta(days=7), 23, 59)
FIRST_LATE = _india(MOVE_IN - timedelta(days=6), 0, 0)


def test_before_the_token_is_in_nothing_comes_back() -> None:
    assert cancellation(_booking(BookingStatus.HELD), EARLY, TERMS) == Cancellation(
        BookingEvent.CANCEL, 0, late=False
    )


def test_a_booking_not_yet_confirmed_gives_the_whole_token_back_at_any_time() -> None:
    on_the_day = _india(MOVE_IN, 9)
    assert cancellation(_booking(BookingStatus.TOKEN_SECURED), on_the_day, TERMS) == Cancellation(
        BookingEvent.CANCEL, TOKEN, late=False
    )


def test_a_confirmed_booking_is_free_to_cancel_until_the_cutoff_by_indias_day() -> None:
    confirmed = _booking(BookingStatus.CONFIRMED)
    assert cancellation(confirmed, LAST_FREE, TERMS) == Cancellation(
        BookingEvent.CANCEL, TOKEN, late=False
    )
    # Refund in full is the only late-cancel rule until Razorpay Route (PRODUCT_CONTEXT §9).
    assert cancellation(confirmed, FIRST_LATE, TERMS) == Cancellation(
        BookingEvent.CANCEL_LATE, TOKEN, late=True
    )


def test_a_late_cancellation_follows_the_terms_rule() -> None:
    kept = replace(TERMS, late_cancel_policy=LateCancelPolicy.FORFEIT_TO_OWNER)
    assert cancellation(_booking(BookingStatus.CONFIRMED), FIRST_LATE, kept) == Cancellation(
        BookingEvent.CANCEL_LATE, 0, late=True
    )
    assert late_refund(TOKEN, LateCancelPolicy.REFUND_FULL) == TOKEN
    with pytest.raises(ValueError, match="shares aren't decided"):
        late_refund(TOKEN, LateCancelPolicy.SPLIT)


@pytest.mark.parametrize(
    "status",
    [
        BookingStatus.CHECKED_IN,
        BookingStatus.DISPUTED,
        BookingStatus.ACTIVE,
        BookingStatus.COMPLETED,
        BookingStatus.EXPIRED,
        BookingStatus.CANCELLED,
        BookingStatus.REJECTED,
        BookingStatus.NO_SHOW,
        BookingStatus.REFUNDED,
    ],
)
def test_once_moved_in_or_ended_a_booking_cant_be_cancelled(status: BookingStatus) -> None:
    assert cancellation(_booking(status), EARLY, TERMS) is None
