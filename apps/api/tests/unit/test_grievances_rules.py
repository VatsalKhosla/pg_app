"""Grievances' rules (step 3.8, ADR 0034), without a database: the deadlines the E-Commerce Rules
set, the moves a grievance may make, lateness and the texts' wording; and the policies the public
pages explain."""

import re
from datetime import UTC, datetime, timedelta

import pytest

from app.core.calendar import INDIA, spoken_date
from app.modules.compliance.domain.grievances import (
    GrievanceStatus,
    acknowledge_by,
    can_move,
    is_late,
    resolve_by,
)
from app.modules.compliance.texts import TEMPLATES
from app.modules.pricing.domain.policies import (
    DEFAULT_BOOKING_POLICY,
    DEFAULT_FEE_POLICY,
    MAX_TOKEN,
    FeeBasis,
    GstMode,
    LateCancelPolicy,
)


def india(year: int, month: int, day: int, hour: int = 11, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=INDIA)


def test_acknowledged_within_48_hours() -> None:
    assert acknowledge_by(india(2027, 7, 15)) == india(2027, 7, 17)


@pytest.mark.parametrize(
    ("received", "due"),
    [
        (india(2027, 7, 15), india(2027, 8, 15)),
        (india(2027, 12, 15), india(2028, 1, 15)),
        # A day the next month doesn't have becomes its last.
        (india(2027, 1, 31), india(2027, 2, 28)),
        (india(2028, 1, 31), india(2028, 2, 29)),
        (india(2027, 3, 31), india(2027, 4, 30)),
        # The month is India's: 1:30 am on 31 January there is still 30 January in UTC.
        (india(2027, 1, 31, 1, 30), india(2027, 2, 28, 1, 30)),
    ],
)
def test_resolved_within_a_calendar_month_in_india(received: datetime, due: datetime) -> None:
    assert resolve_by(received) == due
    assert resolve_by(received.astimezone(UTC)) == due


@pytest.mark.parametrize("current", list(GrievanceStatus))
@pytest.mark.parametrize("target", list(GrievanceStatus))
def test_every_move_a_grievance_may_make(current: GrievanceStatus, target: GrievanceStatus) -> None:
    allowed = {
        (GrievanceStatus.RECEIVED, GrievanceStatus.ACKNOWLEDGED),
        (GrievanceStatus.RECEIVED, GrievanceStatus.RESOLVED),
        (GrievanceStatus.ACKNOWLEDGED, GrievanceStatus.RESOLVED),
    }
    assert can_move(current, target) is ((current, target) in allowed)


def test_late_is_a_missed_deadline_for_the_step_it_waits_on() -> None:
    received = india(2027, 7, 15)
    just_in_time = received + timedelta(hours=48)
    assert not is_late(GrievanceStatus.RECEIVED, received_at=received, now=just_in_time)
    assert is_late(
        GrievanceStatus.RECEIVED, received_at=received, now=just_in_time + timedelta(minutes=1)
    )
    # Acknowledged: only the month counts now.
    assert not is_late(GrievanceStatus.ACKNOWLEDGED, received_at=received, now=india(2027, 8, 15))
    assert is_late(GrievanceStatus.ACKNOWLEDGED, received_at=received, now=india(2027, 8, 16))
    assert not is_late(GrievanceStatus.RESOLVED, received_at=received, now=india(2028, 1, 1))


def test_the_texts_blanks_are_the_ones_filled_in() -> None:
    blanks = {template: set(re.findall(r"\{(\w+)\}", text)) for template, text in TEMPLATES.items()}
    assert blanks == {
        "grievance_received": {"brand", "ticket", "acknowledge_by", "resolve_by"},
        "grievance_acknowledged": {"brand", "ticket", "resolve_by"},
        "grievance_resolved": {"brand", "ticket"},
    }


def test_a_texts_date_is_said_in_india() -> None:
    assert spoken_date(india(2027, 7, 17)) == "Sat 17 Jul"
    # 8 pm in UTC on Friday is already Saturday in India.
    assert spoken_date(datetime(2027, 7, 16, 20, 0, tzinfo=UTC)) == "Sat 17 Jul"


def test_the_policies_in_force_keep_the_founders_rules() -> None:
    # Rule 2 and 3: 30% of the listed rent, with GST at 18% on top until the founders decide.
    fee = DEFAULT_FEE_POLICY
    assert (fee.rate_bps, fee.basis, fee.gst_rate_bps) == (3_000, FeeBasis.LISTED_RENT, 1_800)
    assert fee.gst_mode is GstMode.EXCLUSIVE
    # Rule 8 and 9: a token of at most ₹2,000; free cancellation up to 7 days before moving in.
    booking = DEFAULT_BOOKING_POLICY
    assert booking.token_paise <= MAX_TOKEN == 200_000
    assert (booking.free_cancel_days, booking.check_window_hours) == (7, 24)
    assert booking.late_cancel_policy is LateCancelPolicy.REFUND_FULL
