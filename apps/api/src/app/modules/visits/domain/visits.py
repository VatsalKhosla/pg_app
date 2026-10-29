"""Visits (ARCHITECTURE §11; step 3.7, ADR 0033): a student asks to see a PG at up to three times,
ops schedule one with a field agent, the agent checks in at the building and records how it went.
Pure: no database, no clock (callers pass "now").

The check-in (the time and the agent's position) is the visit log: the proof that we introduced
the student, should the owner later say otherwise (PRODUCT_CONTEXT §6).
"""

from datetime import datetime, time, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.calendar import INDIA

if TYPE_CHECKING:
    from collections.abc import Sequence


class StudentVisitStatus(StrEnum):
    REQUESTED = "requested"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class Outcome(StrEnum):
    """How the visit went, as the agent records it."""

    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    STUDENT_NO_SHOW = "student_no_show"


class CancelledBy(StrEnum):
    STUDENT = "student"
    OPS = "ops"


# Visits a student has open at once (ARCHITECTURE §11), and times they may offer for one.
MAX_OPEN_VISITS: Final = 5
MAX_PREFERRED_STARTS: Final = 3
# When a student may ask to come: on the hour or half past, from 9 am to 7 pm in India, with
# three hours' notice for ops to arrange it, and no more than two weeks ahead.
SLOT_MINUTES: Final = 30
FIRST_START: Final = time(9, 0)
LAST_START: Final = time(19, 0)
MIN_NOTICE: Final = timedelta(hours=3)
HORIZON: Final = timedelta(days=14)
# Ops may book any time from an hour ago (a walk-in) to thirty days ahead.
OPS_PAST: Final = timedelta(hours=1)
OPS_HORIZON: Final = timedelta(days=30)
# An agent may check in from two hours before the visit.
EARLY_CHECK_IN: Final = timedelta(hours=2)
# Reminders before the visit (ARCHITECTURE §11): the day before, and two hours before.
REMINDERS: Final = (("day_before", timedelta(hours=24)), ("two_hours", timedelta(hours=2)))
NOTE_MAX_LENGTH: Final = 500

OPEN: Final = frozenset({StudentVisitStatus.REQUESTED, StudentVisitStatus.SCHEDULED})
# Once ops have scheduled it, the student may see the exact address (CLAUDE.md rule 11); what
# they've seen stays seen.
ENTITLING: Final = frozenset(
    {StudentVisitStatus.SCHEDULED, StudentVisitStatus.COMPLETED, StudentVisitStatus.NO_SHOW}
)

_NEXT: Final = {
    StudentVisitStatus.REQUESTED: frozenset(
        {StudentVisitStatus.SCHEDULED, StudentVisitStatus.CANCELLED}
    ),
    # Scheduled again is a new time or another agent.
    StudentVisitStatus.SCHEDULED: frozenset(
        {
            StudentVisitStatus.SCHEDULED,
            StudentVisitStatus.COMPLETED,
            StudentVisitStatus.NO_SHOW,
            StudentVisitStatus.CANCELLED,
        }
    ),
    StudentVisitStatus.COMPLETED: frozenset[StudentVisitStatus](),
    StudentVisitStatus.NO_SHOW: frozenset[StudentVisitStatus](),
    StudentVisitStatus.CANCELLED: frozenset[StudentVisitStatus](),
}


def can_move(current: StudentVisitStatus, to: StudentVisitStatus) -> bool:
    return to in _NEXT[current]


def next_statuses(current: StudentVisitStatus) -> list[StudentVisitStatus]:
    return sorted(_NEXT[current] - {current})


def start_problems(starts: Sequence[datetime], *, now: datetime) -> list[str]:
    """What's wrong with the times a student offers, in words; none means they're fine."""
    problems: list[str] = []
    if not 1 <= len(starts) <= MAX_PREFERRED_STARTS:
        problems.append(f"offer from 1 to {MAX_PREFERRED_STARTS} times")
    if len(set(starts)) != len(starts):
        problems.append("offer each time once")
    for start in starts:
        local = start.astimezone(INDIA)
        when = local.strftime("%d %b %H:%M")
        if local.minute % SLOT_MINUTES or local.second or local.microsecond:
            problems.append(f"{when}: times start on the hour or half past")
        if not FIRST_START <= local.time() <= LAST_START:
            problems.append(f"{when}: visits start from 9 am to 7 pm")
        if start < now + MIN_NOTICE:
            problems.append(f"{when}: that's less than three hours away")
        if start > now + HORIZON:
            problems.append(f"{when}: that's more than two weeks away")
    return problems


def schedule_problems(at: datetime, *, now: datetime) -> list[str]:
    if at < now - OPS_PAST:
        return ["that time has passed"]
    if at > now + OPS_HORIZON:
        return ["that's more than thirty days away"]
    return []


def may_check_in(scheduled_at: datetime, *, now: datetime) -> bool:
    return now >= scheduled_at - EARLY_CHECK_IN


def status_after(outcome: Outcome) -> StudentVisitStatus:
    return (
        StudentVisitStatus.NO_SHOW
        if outcome is Outcome.STUDENT_NO_SHOW
        else StudentVisitStatus.COMPLETED
    )


def reminders(scheduled_at: datetime, *, now: datetime) -> list[tuple[str, datetime]]:
    """The reminders still to send for a visit at ``scheduled_at``: none for times passed."""
    return [
        (name, scheduled_at - before) for name, before in REMINDERS if scheduled_at - before > now
    ]
