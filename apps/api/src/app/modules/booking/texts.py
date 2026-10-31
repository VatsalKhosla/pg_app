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
CANCELLED_BY_STUDENT: Final = "booking_cancelled_by_student"
# Ops say the student has moved in: the student confirms it themselves (step 5.6).
CONFIRM_MOVE_IN: Final = "booking_confirm_move_in"
MOVED_IN: Final = "booking_moved_in"
SETTLED: Final = "booking_settled"
SETTLED_FOR_OWNER: Final = "booking_settled_for_owner"

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
    CANCELLED_BY_STUDENT: (
        "{brand}: the student cancelled booking {code} at {pg}. The bed is free again."
    ),
    CONFIRM_MOVE_IN: (
        "{brand}: we hear you've moved in at {pg}. Please confirm it on booking {code}: from then "
        "you have {hours} hours to tell us if the room isn't as shown."
    ),
    MOVED_IN: (
        "{brand}: the student has moved in at {pg} (booking {code}). They have until "
        "{window_ends} to tell us if the room isn't as shown."
    ),
    SETTLED: (
        "{brand}: your 24 hours to check the room at {pg} are over, so booking {code} is "
        "settled. Your token counts toward your first month's rent."
    ),
    SETTLED_FOR_OWNER: (
        "{brand}: booking {code} at {pg} is settled: the student moved in and their 24 hours to "
        "check the room have passed."
    ),
}

# Which text each party gets for each change; ops see theirs on the bookings board (5.10).
FOR: Final = {
    (Party.OWNER, BookingEvent.TOKEN_SECURED): TOKEN_IN,
    (Party.STUDENT, BookingEvent.CONFIRM): CONFIRMED,
    (Party.STUDENT, BookingEvent.REJECT): REJECTED,
    (Party.STUDENT, BookingEvent.CONFIRM_TIMEOUT): NOT_CONFIRMED,
    (Party.OWNER, BookingEvent.CONFIRM_TIMEOUT): CONFIRMATION_MISSED,
    (Party.OWNER, BookingEvent.CANCEL): CANCELLED_BY_STUDENT,
    (Party.OWNER, BookingEvent.CANCEL_LATE): CANCELLED_BY_STUDENT,
    # Not a change of its own: ops' nudge while the booking is still confirmed (step 5.6).
    (Party.STUDENT, BookingEvent.CHECK_IN): CONFIRM_MOVE_IN,
    (Party.OWNER, BookingEvent.CHECK_IN): MOVED_IN,
    (Party.STUDENT, BookingEvent.WINDOW_ELAPSED): SETTLED,
    (Party.OWNER, BookingEvent.WINDOW_ELAPSED): SETTLED_FOR_OWNER,
}
