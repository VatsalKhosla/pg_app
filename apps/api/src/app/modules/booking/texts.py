"""The text messages bookings send (steps 5.4 to 5.8, ADRs 0048 and 0050 to 0052): the wording
each DLT template is registered with, and its blanks. A student hears the exact address only once
the booking is confirmed (CLAUDE.md rule 11)."""

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
# A student's report that the room isn't as shown, and how ops settled it (step 5.7).
DISPUTED_FOR_OWNER: Final = "booking_disputed_for_owner"
DISPUTE_REFUNDED: Final = "booking_dispute_refunded"
DISPUTE_REFUNDED_FOR_OWNER: Final = "booking_dispute_refunded_for_owner"
DISPUTE_UPHELD: Final = "booking_dispute_upheld"
DISPUTE_UPHELD_FOR_OWNER: Final = "booking_dispute_upheld_for_owner"
# A student who never moved in (step 5.8): the late-cancel rule says what becomes of the token.
NO_SHOW_REFUNDED: Final = "booking_no_show_refunded"
NO_SHOW_KEPT: Final = "booking_no_show_kept"
NO_SHOW_FOR_OWNER: Final = "booking_no_show_for_owner"

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
    DISPUTED_FOR_OWNER: (
        "{brand}: the student at {pg} has told us the room isn't as shown (booking {code}). We'll "
        "call you to look into it."
    ),
    DISPUTE_REFUNDED: (
        "{brand}: we've looked into booking {code} at {pg}. Your token is refunded in full, and "
        "PGs like it with a bed free are on your booking page."
    ),
    DISPUTE_REFUNDED_FOR_OWNER: (
        "{brand}: after our check, booking {code} at {pg} is cancelled and the student refunded. "
        "The bed is free again."
    ),
    DISPUTE_UPHELD: (
        "{brand}: we've looked into booking {code} at {pg} and found the room as shown, so your "
        "booking stands. Your token counts toward your first month's rent."
    ),
    DISPUTE_UPHELD_FOR_OWNER: (
        "{brand}: after our check, booking {code} at {pg} stands: the student's stay goes ahead."
    ),
    NO_SHOW_REFUNDED: (
        "{brand}: you didn't move in to {pg} by {last_day}, so booking {code} has ended and the "
        "bed is free again. Your token is refunded in full."
    ),
    NO_SHOW_KEPT: (
        "{brand}: you didn't move in to {pg} by {last_day}, so booking {code} has ended and the "
        "bed is free again. Under the cancellation policy, your token isn't refunded."
    ),
    NO_SHOW_FOR_OWNER: (
        "{brand}: the student didn't move in to {pg} by {last_day}, so booking {code} has ended "
        "and the bed is free again."
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
    (Party.OWNER, BookingEvent.DISPUTE): DISPUTED_FOR_OWNER,
    (Party.STUDENT, BookingEvent.RESOLVE_REFUND): DISPUTE_REFUNDED,
    (Party.OWNER, BookingEvent.RESOLVE_REFUND): DISPUTE_REFUNDED_FOR_OWNER,
    (Party.STUDENT, BookingEvent.RESOLVE_UPHOLD): DISPUTE_UPHELD,
    (Party.OWNER, BookingEvent.RESOLVE_UPHOLD): DISPUTE_UPHELD_FOR_OWNER,
    # NO_SHOW_KEPT instead when the booking's late-cancel rule keeps the token.
    (Party.STUDENT, BookingEvent.NO_SHOW): NO_SHOW_REFUNDED,
    (Party.OWNER, BookingEvent.NO_SHOW): NO_SHOW_FOR_OWNER,
}
