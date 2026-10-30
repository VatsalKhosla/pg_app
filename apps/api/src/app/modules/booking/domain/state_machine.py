"""The booking state machine (ARCHITECTURE §7.2 and §7.4; step 5.2, ADR 0045). Pure.

Every change to a booking's status goes through here. A booking opens with `hold`. After that,
`transition` takes:

- the booking's facts;
- an event, and who sent it;
- the moment it arrived;
- the booking's terms.

It answers the next status and the side effects that must happen with it, or refuses. The
services carry out the effects in the same transaction as the status change, and save the change
with a compare-and-set on status and version. A refusal is answered 409 INVALID_TRANSITION.

The table is the founders' rules as §7.2 writes them, and the machine refuses anything not in it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.calendar import india_date

if TYPE_CHECKING:
    from app.modules.pricing.domain.policies import BookingPolicy


class BookingStatus(StrEnum):
    HELD = "held"
    TOKEN_SECURED = "token_secured"  # noqa: S105 - a status, not a secret
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    DISPUTED = "disputed"
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    NO_SHOW = "no_show"
    REFUNDED = "refunded"


class BookingEvent(StrEnum):
    TOKEN_SECURED = "token_secured"  # noqa: S105 - an event, not a secret
    HOLD_EXPIRED = "hold_expired"
    CANCEL = "cancel"
    CONFIRM = "confirm"
    REJECT = "reject"
    CONFIRM_TIMEOUT = "confirm_timeout"
    CANCEL_LATE = "cancel_late"
    OWNER_CANCEL = "owner_cancel"
    CHECK_IN = "check_in"
    NO_SHOW = "no_show"
    DISPUTE = "dispute"
    WINDOW_ELAPSED = "window_elapsed"
    RESOLVE_REFUND = "resolve_refund"
    RESOLVE_UPHOLD = "resolve_uphold"
    MOVE_OUT = "move_out"
    # The token came after its hold expired (§7.4): the bed again if it's still free...
    LATE_PAYMENT_REVIVE = "late_payment_revive"
    # ...or the money straight back if it isn't.
    LATE_PAYMENT_REFUND = "late_payment_refund"


class Party(StrEnum):
    """Who sends an event. The system is the jobs and the gateway's verified events."""

    STUDENT = "student"
    OWNER = "owner"
    OPS = "ops"
    SYSTEM = "system"


# Where the booking holds its bed. COMPLETED keeps it, cut short at the move-out.
ALLOCATED: Final = frozenset(
    {
        BookingStatus.HELD,
        BookingStatus.TOKEN_SECURED,
        BookingStatus.CONFIRMED,
        BookingStatus.CHECKED_IN,
        BookingStatus.DISPUTED,
        BookingStatus.ACTIVE,
        BookingStatus.COMPLETED,
    }
)
# Where the student's token is ours to keep for them: received, not yet earned or given back.
TOKEN_KEPT: Final = frozenset(
    {
        BookingStatus.TOKEN_SECURED,
        BookingStatus.CONFIRMED,
        BookingStatus.CHECKED_IN,
        BookingStatus.DISPUTED,
    }
)
# Statuses no event leaves.
FINAL: Final = frozenset(
    {
        BookingStatus.COMPLETED,
        BookingStatus.CANCELLED,
        BookingStatus.REJECTED,
        BookingStatus.NO_SHOW,
        BookingStatus.REFUNDED,
    }
)


# The side effects a transition asks for, which the services carry out in its transaction.


@dataclass(frozen=True, slots=True)
class ActivateAllocation:
    """Hold the booking's bed for its stay."""


@dataclass(frozen=True, slots=True)
class DeactivateAllocation:
    """Free the booking's bed."""


@dataclass(frozen=True, slots=True)
class TruncateAllocation:
    """End the booking's hold on its bed on ``on``: the day the student moved out."""

    on: date


@dataclass(frozen=True, slots=True)
class SetHoldExpiry:
    at: datetime


@dataclass(frozen=True, slots=True)
class SetConfirmDeadline:
    """The owner confirms by ``at``, or the booking is rejected and the token refunded."""

    at: datetime


@dataclass(frozen=True, slots=True)
class SetCheckWindowEnd:
    at: datetime


@dataclass(frozen=True, slots=True)
class RequestPayment:
    """Ask the gateway for the token: a payment order or a UPI block."""


@dataclass(frozen=True, slots=True)
class CancelPayment:
    """Withdraw the order or block that wasn't paid."""


@dataclass(frozen=True, slots=True)
class RecordTokenReceived:
    """The token came in, and is kept for the student until it's earned."""


@dataclass(frozen=True, slots=True)
class RefundToken:
    """The whole token goes back to the student (or the UPI block is released)."""


@dataclass(frozen=True, slots=True)
class ApplyLateCancelPolicy:
    """The token goes the way the terms' late-cancel rule says (rule 9)."""


@dataclass(frozen=True, slots=True)
class EarnToken:
    """The token is earned: the only point where a booking makes money (rule 8)."""


@dataclass(frozen=True, slots=True)
class IssueOwnerInvoice:
    """The owner's placement-fee invoice, for a tenant who has moved in (rule 2)."""


@dataclass(frozen=True, slots=True)
class OpenDispute:
    """The student says the room isn't as shown."""


@dataclass(frozen=True, slots=True)
class CloseDispute:
    """Ops resolved the dispute: ``refunded`` when the student was right."""

    refunded: bool


@dataclass(frozen=True, slots=True)
class FlagOwner:
    """The owner cancelled a booking they had taken."""


@dataclass(frozen=True, slots=True)
class SuggestSimilar:
    """Help the student book again: similar PGs nearby."""


@dataclass(frozen=True, slots=True)
class AutoConfirm:
    """The PG confirms its bookings itself: `confirm` follows at once, from the system."""


@dataclass(frozen=True, slots=True)
class Notify:
    """Tell ``who`` about this transition."""

    who: Party


type Effect = (
    ActivateAllocation
    | DeactivateAllocation
    | TruncateAllocation
    | SetHoldExpiry
    | SetConfirmDeadline
    | SetCheckWindowEnd
    | RequestPayment
    | CancelPayment
    | RecordTokenReceived
    | RefundToken
    | ApplyLateCancelPolicy
    | EarnToken
    | IssueOwnerInvoice
    | OpenDispute
    | CloseDispute
    | FlagOwner
    | SuggestSimilar
    | AutoConfirm
    | Notify
)


@dataclass(frozen=True, slots=True)
class BookingFacts:
    """What the guards read about a booking."""

    status: BookingStatus
    move_in: date
    token_paise: int
    instant_confirm: bool
    hold_expires_at: datetime | None = None
    confirm_by: datetime | None = None
    check_window_ends_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Moment:
    """When an event arrived, and what came with it."""

    now: datetime
    # A verified payment's amount, for token_secured and a late payment.
    paid_paise: int | None = None
    # Whether the bed is still free, for a late payment.
    bed_free: bool | None = None
    # The day the student moved out, for move_out.
    moved_out_on: date | None = None

    @property
    def today(self) -> date:
        """The day in India."""
        return india_date(self.now)


@dataclass(frozen=True, slots=True)
class Transition:
    to: BookingStatus
    effects: tuple[Effect, ...]


class TransitionRefusedError(Exception):
    """The event doesn't apply to the booking now: the wrong status, the wrong party, or a guard
    that doesn't hold. The services answer 409 INVALID_TRANSITION with ``reason``."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class _Ask:
    facts: BookingFacts
    party: Party
    moment: Moment
    policy: BookingPolicy


# What stops a transition, in words (None when nothing does), and what it does.
type _Guard = Callable[[_Ask], str | None]
type _Effects = Callable[[_Ask], tuple[Effect, ...]]


@dataclass(frozen=True, slots=True)
class _Rule:
    to: BookingStatus
    parties: frozenset[Party]
    guard: _Guard
    effects: _Effects


def _always(_ask: _Ask) -> str | None:
    return None


def _token_paid(ask: _Ask) -> str | None:
    if ask.moment.paid_paise != ask.facts.token_paise:
        return "the payment isn't the booking's token"
    return None


def _hold_over(ask: _Ask) -> str | None:
    expires_at = ask.facts.hold_expires_at
    if expires_at is None or ask.moment.now < expires_at:
        return "the hold hasn't expired"
    return None


def _confirmable(ask: _Ask) -> str | None:
    if ask.party is Party.SYSTEM and not ask.facts.instant_confirm:
        return "the owner confirms this PG's bookings"
    return None


def _confirm_late(ask: _Ask) -> str | None:
    confirm_by = ask.facts.confirm_by
    if confirm_by is None or ask.moment.now < confirm_by:
        return "the owner still has time to confirm"
    return None


def _free_cancel_ends(ask: _Ask) -> date:
    """The last day a confirmed booking is cancelled for free (rule 9)."""
    return ask.facts.move_in - timedelta(days=ask.policy.free_cancel_days)


def _cancel_free(ask: _Ask) -> str | None:
    if ask.moment.today > _free_cancel_ends(ask):
        return f"free cancellation ended {ask.policy.free_cancel_days} days before the move-in"
    return None


def _cancel_late(ask: _Ask) -> str | None:
    if ask.moment.today <= _free_cancel_ends(ask):
        return "cancelling now is free"
    return None


def _check_in_open(ask: _Ask) -> str | None:
    if ask.moment.today < ask.facts.move_in - timedelta(days=1):
        return "checking in opens the day before the move-in"
    return None


def _no_show(ask: _Ask) -> str | None:
    if ask.moment.today <= ask.facts.move_in + timedelta(days=ask.policy.no_show_days):
        return f"a student has {ask.policy.no_show_days} days after the move-in to arrive"
    return None


def _window_open(ask: _Ask) -> str | None:
    ends_at = ask.facts.check_window_ends_at
    if ends_at is None or ask.moment.now >= ends_at:
        return "the time to report a problem with the room has passed"
    return None


def _window_over(ask: _Ask) -> str | None:
    ends_at = ask.facts.check_window_ends_at
    if ends_at is None or ask.moment.now < ends_at:
        return "the time to report a problem with the room hasn't passed"
    return None


def _moved_out(ask: _Ask) -> str | None:
    moved_out_on = ask.moment.moved_out_on
    if moved_out_on is None or moved_out_on <= ask.facts.move_in:
        return "a move-out comes after the move-in"
    if moved_out_on > ask.moment.today:
        return "a move-out is recorded once it has happened"
    return None


def _revivable(ask: _Ask) -> str | None:
    if (problem := _token_paid(ask)) is not None:
        return problem
    if ask.moment.bed_free is not True:
        return "the bed has gone"
    return None


def _refundable(ask: _Ask) -> str | None:
    if (problem := _token_paid(ask)) is not None:
        return problem
    if ask.moment.bed_free is not False:
        return "the bed is still free, so the booking takes the payment"
    return None


def _fixed(*effects: Effect) -> _Effects:
    def effects_of(_ask: _Ask) -> tuple[Effect, ...]:
        return effects

    return effects_of


def _secured(ask: _Ask) -> tuple[Effect, ...]:
    """The token is in: kept for the student, the owner and ops told, and a deadline for the
    owner to confirm, unless the PG confirms its bookings itself."""
    deadline = ask.moment.now + timedelta(hours=ask.policy.confirm_deadline_hours)
    effects: tuple[Effect, ...] = (
        RecordTokenReceived(),
        SetConfirmDeadline(deadline),
        Notify(Party.OWNER),
        Notify(Party.OPS),
    )
    return (*effects, AutoConfirm()) if ask.facts.instant_confirm else effects


def _revived(ask: _Ask) -> tuple[Effect, ...]:
    return (ActivateAllocation(), *_secured(ask))


def _checked_in(ask: _Ask) -> tuple[Effect, ...]:
    ends_at = ask.moment.now + timedelta(hours=ask.policy.check_window_hours)
    return (SetCheckWindowEnd(ends_at), Notify(Party.OWNER))


def _completed(ask: _Ask) -> tuple[Effect, ...]:
    assert ask.moment.moved_out_on is not None  # noqa: S101 - the guard asked for it
    return (TruncateAllocation(ask.moment.moved_out_on),)


# Rule 8: no money is earned until the student has moved in and the check passed.
_EARNED: Final = (EarnToken(), IssueOwnerInvoice(), Notify(Party.STUDENT), Notify(Party.OWNER))
# The bed freed, the whole token back, and help to book again.
_RELEASED: Final = (DeactivateAllocation(), RefundToken(), SuggestSimilar())

_STUDENT: Final = frozenset({Party.STUDENT})
_OPS: Final = frozenset({Party.OPS})
_SYSTEM: Final = frozenset({Party.SYSTEM})
_OWNER_OR_OPS: Final = frozenset({Party.OWNER, Party.OPS})


def _owner_cancel() -> _Rule:
    return _Rule(
        BookingStatus.CANCELLED,
        _OWNER_OR_OPS,
        _always,
        _fixed(*_RELEASED, FlagOwner(), Notify(Party.STUDENT), Notify(Party.OPS)),
    )


# §7.2 and §7.4, row by row.
_TABLE: Final[dict[tuple[BookingStatus, BookingEvent], _Rule]] = {
    (BookingStatus.HELD, BookingEvent.TOKEN_SECURED): _Rule(
        BookingStatus.TOKEN_SECURED, _SYSTEM, _token_paid, _secured
    ),
    (BookingStatus.HELD, BookingEvent.HOLD_EXPIRED): _Rule(
        BookingStatus.EXPIRED,
        _SYSTEM,
        _hold_over,
        _fixed(DeactivateAllocation(), CancelPayment()),
    ),
    (BookingStatus.HELD, BookingEvent.CANCEL): _Rule(
        BookingStatus.CANCELLED,
        _STUDENT,
        _always,
        _fixed(DeactivateAllocation(), CancelPayment()),
    ),
    (BookingStatus.TOKEN_SECURED, BookingEvent.CONFIRM): _Rule(
        BookingStatus.CONFIRMED,
        _OWNER_OR_OPS | _SYSTEM,
        _confirmable,
        _fixed(Notify(Party.STUDENT)),
    ),
    (BookingStatus.TOKEN_SECURED, BookingEvent.REJECT): _Rule(
        BookingStatus.REJECTED,
        _OWNER_OR_OPS,
        _always,
        _fixed(*_RELEASED, Notify(Party.STUDENT)),
    ),
    (BookingStatus.TOKEN_SECURED, BookingEvent.CONFIRM_TIMEOUT): _Rule(
        BookingStatus.REJECTED,
        _SYSTEM,
        _confirm_late,
        _fixed(*_RELEASED, Notify(Party.STUDENT), Notify(Party.OWNER), Notify(Party.OPS)),
    ),
    (BookingStatus.TOKEN_SECURED, BookingEvent.CANCEL): _Rule(
        BookingStatus.CANCELLED,
        _STUDENT,
        _always,
        _fixed(DeactivateAllocation(), RefundToken(), Notify(Party.OWNER)),
    ),
    (BookingStatus.TOKEN_SECURED, BookingEvent.OWNER_CANCEL): _owner_cancel(),
    (BookingStatus.CONFIRMED, BookingEvent.CANCEL): _Rule(
        BookingStatus.CANCELLED,
        _STUDENT,
        _cancel_free,
        _fixed(DeactivateAllocation(), RefundToken(), Notify(Party.OWNER)),
    ),
    (BookingStatus.CONFIRMED, BookingEvent.CANCEL_LATE): _Rule(
        BookingStatus.CANCELLED,
        _STUDENT,
        _cancel_late,
        _fixed(DeactivateAllocation(), ApplyLateCancelPolicy(), Notify(Party.OWNER)),
    ),
    (BookingStatus.CONFIRMED, BookingEvent.OWNER_CANCEL): _owner_cancel(),
    # Ops may mark a move-in, but the student's confirmation is what moves the booking (5.6),
    # so the check window that decides when the token is earned starts on their word.
    (BookingStatus.CONFIRMED, BookingEvent.CHECK_IN): _Rule(
        BookingStatus.CHECKED_IN, _STUDENT, _check_in_open, _checked_in
    ),
    (BookingStatus.CONFIRMED, BookingEvent.NO_SHOW): _Rule(
        BookingStatus.NO_SHOW,
        _SYSTEM,
        _no_show,
        _fixed(
            DeactivateAllocation(),
            ApplyLateCancelPolicy(),
            Notify(Party.STUDENT),
            Notify(Party.OWNER),
        ),
    ),
    (BookingStatus.CHECKED_IN, BookingEvent.DISPUTE): _Rule(
        BookingStatus.DISPUTED,
        _STUDENT,
        _window_open,
        _fixed(OpenDispute(), Notify(Party.OPS), Notify(Party.OWNER)),
    ),
    (BookingStatus.CHECKED_IN, BookingEvent.WINDOW_ELAPSED): _Rule(
        BookingStatus.ACTIVE, _SYSTEM, _window_over, _fixed(*_EARNED)
    ),
    (BookingStatus.DISPUTED, BookingEvent.RESOLVE_REFUND): _Rule(
        BookingStatus.REFUNDED,
        _OPS,
        _always,
        _fixed(
            CloseDispute(refunded=True),
            *_RELEASED,
            Notify(Party.STUDENT),
            Notify(Party.OWNER),
        ),
    ),
    (BookingStatus.DISPUTED, BookingEvent.RESOLVE_UPHOLD): _Rule(
        BookingStatus.ACTIVE, _OPS, _always, _fixed(CloseDispute(refunded=False), *_EARNED)
    ),
    (BookingStatus.ACTIVE, BookingEvent.MOVE_OUT): _Rule(
        BookingStatus.COMPLETED, _STUDENT | _OWNER_OR_OPS, _moved_out, _completed
    ),
    (BookingStatus.EXPIRED, BookingEvent.LATE_PAYMENT_REVIVE): _Rule(
        BookingStatus.TOKEN_SECURED, _SYSTEM, _revivable, _revived
    ),
    (BookingStatus.EXPIRED, BookingEvent.LATE_PAYMENT_REFUND): _Rule(
        BookingStatus.EXPIRED,
        _SYSTEM,
        _refundable,
        _fixed(RecordTokenReceived(), RefundToken(), SuggestSimilar(), Notify(Party.STUDENT)),
    ),
}

# The (status, event) pairs the table allows. The machine refuses every other pair.
ALLOWED: Final = frozenset(_TABLE)

# What each event does to a booking, for a refusal's words.
_DOING: Final = {
    BookingEvent.TOKEN_SECURED: "take a token",
    BookingEvent.HOLD_EXPIRED: "expire",
    BookingEvent.CANCEL: "be cancelled",
    BookingEvent.CONFIRM: "be confirmed",
    BookingEvent.REJECT: "be rejected",
    BookingEvent.CONFIRM_TIMEOUT: "time out unconfirmed",
    BookingEvent.CANCEL_LATE: "be cancelled late",
    BookingEvent.OWNER_CANCEL: "be cancelled by the owner",
    BookingEvent.CHECK_IN: "be checked in",
    BookingEvent.NO_SHOW: "be marked a no-show",
    BookingEvent.DISPUTE: "be disputed",
    BookingEvent.WINDOW_ELAPSED: "start",
    BookingEvent.RESOLVE_REFUND: "be refunded",
    BookingEvent.RESOLVE_UPHOLD: "be upheld",
    BookingEvent.MOVE_OUT: "be moved out of",
    BookingEvent.LATE_PAYMENT_REVIVE: "take a late payment",
    BookingEvent.LATE_PAYMENT_REFUND: "refund a late payment",
}


def hold(*, now: datetime, policy: BookingPolicy) -> Transition:
    """A new booking, HELD: its bed held, a hold that lasts the terms' minutes, and the token
    asked for. The services check first what a hold needs (§7.3): an unexpired quote of the
    student's, a free bed, and fewer active holds than the terms allow."""
    return Transition(
        BookingStatus.HELD,
        (
            ActivateAllocation(),
            SetHoldExpiry(now + timedelta(minutes=policy.hold_minutes)),
            RequestPayment(),
        ),
    )


def transition(
    facts: BookingFacts,
    event: BookingEvent,
    party: Party,
    moment: Moment,
    policy: BookingPolicy,
) -> Transition:
    """The booking's next status after ``event`` from ``party`` at ``moment``, with the side
    effects that go with it. ``policy`` is the booking's own terms. Raises
    TransitionRefusedError for anything the table doesn't allow."""
    rule = _TABLE.get((facts.status, event))
    if rule is None:
        status = facts.status.replace("_", "-")
        msg = f"A {status} booking can't {_DOING[event]}."
        raise TransitionRefusedError(msg)
    if party not in rule.parties:
        msg = f"That's not for the {party} to do."
        raise TransitionRefusedError(msg)
    ask = _Ask(facts, party, moment, policy)
    if (problem := rule.guard(ask)) is not None:
        msg = f"{problem[0].upper()}{problem[1:]}."
        raise TransitionRefusedError(msg)
    return Transition(rule.to, rule.effects(ask))
