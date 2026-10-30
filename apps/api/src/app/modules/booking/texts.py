"""The text messages bookings send (step 5.4, ADR 0048): the wording each DLT template is
registered with, and its blanks. A student hears the exact address only once the booking is
confirmed (CLAUDE.md rule 11)."""

from typing import Final

from app.modules.booking.domain.state_machine import BookingEvent, Party

TOKEN_IN: Final = "booking_token_in"  # noqa: S105 - a template name, not a secret
# The same news for a PG that confirms its bookings itself: nothing for the owner to do.
NEW_CONFIRMED: Final = "booking_new_confirmed"
CONFIRMED: Final = "booking_confirmed"
REJECTED: Final = "booking_rejected"
NOT_CONFIRMED: Final = "booking_not_confirmed"
CONFIRMATION_MISSED: Final = "booking_confirmation_missed"

TEMPLATES: Final = {
    TOKEN_IN: (
        "{brand}: a student has booked a bed at {pg}: {room_type}, moving in on {move_in}. "
        "Booking {code}. Please confirm it by {confirm_by}, or it is cancelled and refunded."
    ),
    NEW_CONFIRMED: (
        "{brand}: a student has booked a bed at {pg}: {room_type}, moving in on {move_in}. "
        "Booking {code} is confirmed."
    ),
    CONFIRMED: (
        "{brand}: booking {code} at {pg} is confirmed. You move in on {move_in}. "
        "Address: {address}."
    ),
    REJECTED: (
        "{brand}: {pg} couldn't take booking {code}. Your token is refunded in full, and we'll "
        "help you find another PG."
    ),
    NOT_CONFIRMED: (
        "{brand}: {pg} didn't confirm booking {code} in time, so it's cancelled. Your token is "
        "refunded in full, and we'll help you find another PG."
    ),
    CONFIRMATION_MISSED: (
        "{brand}: booking {code} at {pg} wasn't confirmed in time, so it's cancelled and the "
        "student refunded."
    ),
}

# Which text each party gets for each change; ops see theirs on the bookings board (5.10).
FOR: Final = {
    (Party.OWNER, BookingEvent.TOKEN_SECURED): TOKEN_IN,
    (Party.STUDENT, BookingEvent.CONFIRM): CONFIRMED,
    (Party.STUDENT, BookingEvent.REJECT): REJECTED,
    (Party.STUDENT, BookingEvent.CONFIRM_TIMEOUT): NOT_CONFIRMED,
    (Party.OWNER, BookingEvent.CONFIRM_TIMEOUT): CONFIRMATION_MISSED,
}
