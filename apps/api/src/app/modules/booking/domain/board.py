"""What ops watch on the bookings board (step 5.10, ADR 0054): which bookings need a person now,
since when and by when, and what ops may do with each. Pure: callers pass "now".

- **The owner's answer:** a token is in, and two hours later ops call the owner. The booking
  rejects itself later still, at its own deadline.
- **A dispute:** settled the same day it was reported, in India (rule 8).
- **A move-in:** due on its day, in India. The student says they've moved in, or ops nudge them,
  until the terms' wait runs out and the booking ends as a no-show.
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.calendar import INDIA, india_date
from app.modules.booking.domain.state_machine import (
    BookingEvent,
    BookingStatus,
    Party,
    allows,
)

if TYPE_CHECKING:
    from datetime import date

    from app.modules.booking.domain.state_machine import BookingFacts, Moment
    from app.modules.pricing.domain.policies import BookingPolicy

# How long a token waits for its owner before ops step in.
UNCONFIRMED_SLA: Final = timedelta(hours=2)
# Bookings still moving, worked oldest first; the others are looked up, newest first.
QUEUES: Final = frozenset(
    {
        BookingStatus.HELD,
        BookingStatus.TOKEN_SECURED,
        BookingStatus.CONFIRMED,
        BookingStatus.CHECKED_IN,
        BookingStatus.DISPUTED,
    }
)


class TimerKind(StrEnum):
    UNCONFIRMED = "unconfirmed"
    DISPUTE = "dispute"
    MOVE_IN = "move_in"


class OpsAction(StrEnum):
    """What ops may do with a booking now, each as the state machine allows it."""

    CONFIRM = "confirm"
    REJECT = "reject"
    OWNER_CANCEL = "owner_cancel"
    REMIND_MOVE_IN = "remind_move_in"
    MOVE_OUT = "move_out"


@dataclass(frozen=True, slots=True)
class BoardTimer:
    """What a booking is waiting for: since when, and from when that's late."""

    kind: TimerKind
    since: datetime
    due: datetime

    def late(self, now: datetime) -> bool:
        return now >= self.due


def _midnight(day: date) -> datetime:
    """The start of ``day`` in India, in UTC as every other time the API gives."""
    return datetime.combine(day, time.min, tzinfo=INDIA).astimezone(UTC)


def timer_of(
    status: BookingStatus,
    *,
    token_secured_at: datetime | None,
    disputed_at: datetime | None,
    move_in: date,
    now: datetime,
) -> BoardTimer | None:
    """The clock a booking is on now, if any."""
    match status:
        case BookingStatus.TOKEN_SECURED if token_secured_at is not None:
            return BoardTimer(
                TimerKind.UNCONFIRMED, token_secured_at, token_secured_at + UNCONFIRMED_SLA
            )
        case BookingStatus.DISPUTED if disputed_at is not None:
            next_day = india_date(disputed_at) + timedelta(days=1)
            return BoardTimer(TimerKind.DISPUTE, disputed_at, _midnight(next_day))
        case BookingStatus.CONFIRMED if india_date(now) >= move_in:
            next_day = move_in + timedelta(days=1)
            return BoardTimer(TimerKind.MOVE_IN, _midnight(move_in), _midnight(next_day))
        case _:
            return None


def needs_attention(timer: BoardTimer | None, now: datetime) -> bool:
    """Whether ops should act now: an owner past their two hours, any open dispute, any move-in
    due. A token just in is the owner's to answer first."""
    if timer is None:
        return False
    return timer.kind is not TimerKind.UNCONFIRMED or timer.late(now)


def ops_actions(facts: BookingFacts, moment: Moment, policy: BookingPolicy) -> list[OpsAction]:
    """What the board offers: exactly what the state machine would take from ops at ``moment``,
    so the page never offers what the API would refuse. Reminding a student asks whether they
    could say they've moved in, as only they can."""
    actions = []
    if allows(facts, BookingEvent.CONFIRM, Party.OPS, moment, policy):
        actions.append(OpsAction.CONFIRM)
    if allows(facts, BookingEvent.REJECT, Party.OPS, moment, policy):
        actions.append(OpsAction.REJECT)
    if allows(facts, BookingEvent.OWNER_CANCEL, Party.OPS, moment, policy):
        actions.append(OpsAction.OWNER_CANCEL)
    if allows(facts, BookingEvent.CHECK_IN, Party.STUDENT, moment, policy):
        actions.append(OpsAction.REMIND_MOVE_IN)
    moved_out_today = replace(moment, moved_out_on=moment.today)
    if allows(facts, BookingEvent.MOVE_OUT, Party.OPS, moved_out_today, policy):
        actions.append(OpsAction.MOVE_OUT)
    return actions
