"""The booking module's errors (ARCHITECTURE §15)."""

from app.core.errors import AppError


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
