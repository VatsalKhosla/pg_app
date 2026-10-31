"""What cancelling a booking now would mean for the student (step 5.5, ADR 0049). Pure.

The student sees it before they confirm, and the API checks it again as they do (rule 9):

- **before the token is in,** nothing has been paid, so nothing comes back;
- **once it's in and until the free-cancellation cutoff,** the whole token comes back;
- **later,** the token goes as the booking's late-cancel rule says.

Which applies is the state machine's own answer, so this never disagrees with it.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.booking.domain.state_machine import (
    BookingEvent,
    BookingStatus,
    Party,
    TransitionRefusedError,
    transition,
)
from app.modules.pricing.domain.policies import LateCancelPolicy

if TYPE_CHECKING:
    from app.modules.booking.domain.state_machine import BookingFacts, Moment
    from app.modules.pricing.domain.policies import BookingPolicy


@dataclass(frozen=True, slots=True)
class Cancellation:
    event: BookingEvent
    # What the student gets back, in paise.
    refund_paise: int
    # Past the free-cancellation cutoff: the late-cancel rule decides the refund.
    late: bool


def late_refund(token_paise: int, rule: LateCancelPolicy) -> int:
    """The part of the token a late cancellation gives back."""
    match rule:
        case LateCancelPolicy.REFUND_FULL:
            return token_paise
        case LateCancelPolicy.FORFEIT_TO_OWNER:
            return 0
        case LateCancelPolicy.SPLIT:
            # The founders decide the shares when payments go through Razorpay Route; until then
            # the booking policy refuses this rule (pricing.domain.policies).
            msg = "a split's shares aren't decided yet"
            raise ValueError(msg)


def cancellation(facts: BookingFacts, moment: Moment, policy: BookingPolicy) -> Cancellation | None:
    """Cancelling the booking at ``moment``; None when the student can't cancel it now."""
    for event in (BookingEvent.CANCEL, BookingEvent.CANCEL_LATE):
        try:
            transition(facts, event, Party.STUDENT, moment, policy)
        except TransitionRefusedError:
            continue
        if event is BookingEvent.CANCEL_LATE:
            refund = late_refund(facts.token_paise, policy.late_cancel_policy)
        elif facts.status is BookingStatus.HELD:
            refund = 0
        else:
            refund = facts.token_paise
        return Cancellation(event, refund, late=event is BookingEvent.CANCEL_LATE)
    return None
