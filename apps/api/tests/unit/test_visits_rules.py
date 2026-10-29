"""Visits' rules (step 3.7, ADR 0033), without a database: the times a student may offer, the
moves a visit may make, check-in and outcomes, reminders, and the texts' wording."""

import re
from datetime import UTC, datetime, timedelta

import pytest

from app.core.calendar import INDIA
from app.modules.visits.domain.visits import (
    Outcome,
    StudentVisitStatus,
    can_move,
    may_check_in,
    next_statuses,
    reminders,
    schedule_problems,
    start_problems,
    status_after,
)
from app.modules.visits.service import when
from app.modules.visits.texts import TEMPLATES

# Wednesday 14 July 2027, 3:30 pm in India.
NOW = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)


def india(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2027, 7, day, hour, minute, tzinfo=INDIA)


def test_good_times_have_no_problems() -> None:
    assert start_problems([india(15, 11), india(15, 18, 30), india(20, 9)], now=NOW) == []


@pytest.mark.parametrize(
    ("starts", "problem"),
    [
        ([], "offer from 1 to 3 times"),
        ([india(15, 11), india(15, 12), india(15, 13), india(15, 14)], "offer from 1 to 3 times"),
        ([india(15, 11), india(15, 11)], "offer each time once"),
        ([india(15, 11, 15)], "on the hour or half past"),
        ([india(15, 8, 30)], "from 9 am to 7 pm"),
        ([india(15, 19, 30)], "from 9 am to 7 pm"),
        ([india(14, 17)], "less than three hours away"),
        ([india(29, 11)], "more than two weeks away"),
    ],
)
def test_times_that_dont_work_say_why(starts: list[datetime], problem: str) -> None:
    assert any(problem in found for found in start_problems(starts, now=NOW))


def test_visiting_hours_are_india_time_whatever_the_zone_sent() -> None:
    # 11 am in India, sent as UTC.
    assert start_problems([india(15, 11).astimezone(UTC)], now=NOW) == []


def test_ops_may_book_from_an_hour_ago_to_thirty_days_ahead() -> None:
    assert schedule_problems(NOW - timedelta(minutes=59), now=NOW) == []
    assert schedule_problems(NOW - timedelta(hours=2), now=NOW) == ["that time has passed"]
    assert schedule_problems(NOW + timedelta(days=31), now=NOW) != []


@pytest.mark.parametrize("current", list(StudentVisitStatus))
@pytest.mark.parametrize("to", list(StudentVisitStatus))
def test_every_move_a_visit_may_make(current: StudentVisitStatus, to: StudentVisitStatus) -> None:
    allowed = {
        (StudentVisitStatus.REQUESTED, StudentVisitStatus.SCHEDULED),
        (StudentVisitStatus.REQUESTED, StudentVisitStatus.CANCELLED),
        (StudentVisitStatus.SCHEDULED, StudentVisitStatus.SCHEDULED),
        (StudentVisitStatus.SCHEDULED, StudentVisitStatus.COMPLETED),
        (StudentVisitStatus.SCHEDULED, StudentVisitStatus.NO_SHOW),
        (StudentVisitStatus.SCHEDULED, StudentVisitStatus.CANCELLED),
    }
    assert can_move(current, to) is ((current, to) in allowed)


def test_next_statuses_leave_out_staying_put() -> None:
    assert next_statuses(StudentVisitStatus.SCHEDULED) == [
        StudentVisitStatus.CANCELLED,
        StudentVisitStatus.COMPLETED,
        StudentVisitStatus.NO_SHOW,
    ]
    assert next_statuses(StudentVisitStatus.COMPLETED) == []


def test_an_agent_checks_in_from_two_hours_before() -> None:
    at = NOW + timedelta(hours=3)
    assert not may_check_in(at, now=NOW)
    assert may_check_in(at, now=NOW + timedelta(hours=1))
    assert may_check_in(at, now=NOW + timedelta(hours=8))


def test_a_student_who_didnt_come_is_a_no_show() -> None:
    assert status_after(Outcome.STUDENT_NO_SHOW) is StudentVisitStatus.NO_SHOW
    assert status_after(Outcome.INTERESTED) is StudentVisitStatus.COMPLETED
    assert status_after(Outcome.NOT_INTERESTED) is StudentVisitStatus.COMPLETED


def test_reminders_the_day_before_and_two_hours_before_unless_past() -> None:
    at = NOW + timedelta(days=2)
    assert reminders(at, now=NOW) == [
        ("day_before", at - timedelta(hours=24)),
        ("two_hours", at - timedelta(hours=2)),
    ]
    assert reminders(NOW + timedelta(hours=5), now=NOW) == [("two_hours", NOW + timedelta(hours=3))]
    assert reminders(NOW + timedelta(hours=1), now=NOW) == []


def test_a_texts_time_is_said_in_india() -> None:
    assert when(india(15, 11, 30)) == "Thu 15 Jul, 11:30 am"
    assert when(india(15, 12)) == "Thu 15 Jul, 12:00 pm"
    assert when(india(15, 18).astimezone(UTC)) == "Thu 15 Jul, 6:00 pm"


def test_the_texts_blanks_are_the_ones_filled_in() -> None:
    blanks = {template: set(re.findall(r"\{(\w+)\}", text)) for template, text in TEMPLATES.items()}
    assert blanks == {
        "visit_scheduled": {"brand", "pg", "when", "address"},
        "visit_reminder": {"brand", "pg", "when", "address"},
        # A cancelled visit's text has no need of the address.
        "visit_cancelled": {"brand", "pg", "when"},
    }
