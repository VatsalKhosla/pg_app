"""The booking module's errors (ARCHITECTURE §15)."""

from typing import TYPE_CHECKING

from app.core.errors import AppError

if TYPE_CHECKING:
    from collections.abc import Sequence


class BookingNeedsVisitError(AppError):
    """Remote booking is off (season one is visit-first): beds are reserved on a visit."""

    status = 409
    code = "BOOKING_NEEDS_VISIT"
    title = "Beds are reserved on a visit for now"


class HoldLimitReachedError(AppError):
    """The student holds as many beds as the booking terms allow at once."""

    status = 409
    code = "HOLD_LIMIT_REACHED"
    title = "You're holding as many beds as you can at once"


class QuoteUsedError(AppError):
    """A booking took this quote already: each quote makes one booking."""

    status = 409
    code = "QUOTE_USED"
    title = "That price was used for a booking already"


class RefundChangedError(AppError):
    """What cancelling gives back isn't what the student was shown: the day turned past the
    free-cancellation cutoff, say. They look again before cancelling."""

    status = 409
    code = "REFUND_CHANGED"
    title = "What cancelling gives back has changed"


class DisputeInvalidError(AppError):
    """A report the rules refuse, such as a photo that isn't the student's own or isn't ready
    yet. The detail names every problem at once."""

    status = 422
    code = "DISPUTE_INVALID"
    title = "That report can't be sent as it is"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)
