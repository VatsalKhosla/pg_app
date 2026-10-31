"""The bookings API's shapes (ARCHITECTURE §15; ADRs 0046 to 0051)."""

import uuid
from datetime import date, datetime
from typing import Final

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.booking.domain.disputes import (
    DESCRIPTION_MAX_LENGTH,
    DESCRIPTION_MIN_LENGTH,
    MAX_PHOTOS,
    NOTES_MAX_LENGTH,
    DisputeReason,
    DisputeStatus,
    Outcome,
)
from app.modules.booking.domain.state_machine import BookingStatus, Party
from app.modules.catalog.domain.listing import GenderPolicy
from app.modules.catalog.domain.rooms import Occupancy

REASON_MAX_LENGTH: Final = 500


class HoldRequest(ApiModel):
    # The student's own quote, unexpired: the booking copies its money.
    quote: uuid.UUID


class BookingPlace(ApiModel):
    slug: str
    name: str
    locality: str


class TimelineEntry(ApiModel):
    """One change to the booking, as its history has it."""

    # "hold" for the first, then the state machine's event.
    event: str
    status: BookingStatus
    by: Party
    at: datetime


class CancellationTerms(ApiModel):
    """What cancelling now would mean (rule 9): the refund, and whether the free-cancellation
    cutoff has passed, so the late-cancel rule decides it."""

    refund_paise: int
    late: bool


class StudentDispute(ApiModel):
    """The student's report that the room isn't as shown, and where it stands."""

    reason: DisputeReason
    status: DisputeStatus
    opened_at: datetime
    resolved_at: datetime | None


class RebookSearch(ApiModel):
    """A search for PGs like this one with a bed free for the student's move-in, once a booking
    ended through no fault of theirs: its filters, as the search API takes them (step 5.7)."""

    locality: str
    occupancy: Occupancy
    gender: GenderPolicy
    move_in_month: str
    budget_max_paise: int


class StudentBooking(ApiModel):
    """A booking as its student sees it: the quote's money, fixed for the stay (rule 5). The
    exact address and the owner's phone show once the owner confirms (rule 11), from the PG's
    contact."""

    code: str
    status: BookingStatus
    property: BookingPlace
    room_type: str
    move_in: date
    stay_months: int
    planned_move_out: date
    # While HELD, the token must be paid by then: the one countdown the student sees.
    hold_expires_at: datetime
    # Once the token is in: the owner confirms by then, or the token comes back in full.
    confirm_by: datetime | None
    # Once confirmed: the day the student may say they've moved in, and whether they may now.
    check_in_opens_on: date | None
    can_check_in: bool
    # How long the student has, once moved in, to tell us if the room isn't as shown (the
    # booking's terms; 24 hours by default)...
    check_window_hours: int
    # ...and, once they have, when that time ends: the one countdown besides a hold's.
    check_window_ends_at: datetime | None
    monthly_rent_paise: int
    token_paise: int
    due_at_move_in_paise: int
    deposit_paise: int
    monthly_charges_paise: int
    one_time_charges_paise: int
    created_at: datetime
    # Oldest first.
    timeline: list[TimelineEntry]
    # Null when it can't be cancelled now: checked in, or over.
    cancellation: CancellationTerms | None
    # While their time to check the room lasts, they may report that it isn't as shown.
    can_dispute: bool
    dispute: StudentDispute | None
    # Help to book again, once the booking ended through no fault of the student's.
    rebook: RebookSearch | None


class StudentBookingList(ApiModel):
    # Newest first.
    items: list[StudentBooking]


class CancelRequest(ApiModel):
    # The refund the student was shown: if cancelling now means something else, nothing changes.
    refund_paise: int = Field(ge=0)


class BookingStudent(ApiModel):
    # Their first name, when they gave one.
    name: str | None


class ManagedBooking(ApiModel):
    """A booking as its owner or ops see it, to confirm or reject it (step 5.4, ADR 0048)."""

    code: str
    status: BookingStatus
    property: BookingPlace
    room_type: str
    room: str
    bed: str
    move_in: date
    stay_months: int
    planned_move_out: date
    monthly_rent_paise: int
    token_paise: int
    due_at_move_in_paise: int
    deposit_paise: int
    hold_expires_at: datetime
    # Once the token is in: the owner confirms by then, or the booking is rejected and refunded.
    confirm_by: datetime | None
    # Once the student says they've moved in: when, and the end of their 24 hours to check the room.
    checked_in_at: datetime | None
    check_window_ends_at: datetime | None
    student: BookingStudent
    created_at: datetime


class MoveInReminder(ApiModel):
    """Ops' nudge to a student who has moved in to say so (step 5.6)."""

    # False when they were already asked today: one text a day at most.
    sent: bool


class RejectRequest(ApiModel):
    # Why, for the student's record and ops; never shown to other students.
    reason: str = Field(min_length=1, max_length=REASON_MAX_LENGTH)


class DisputeRequest(ApiModel):
    """The student's report that their room isn't as shown (step 5.7, ADR 0051)."""

    reason: DisputeReason
    description: str = Field(min_length=DESCRIPTION_MIN_LENGTH, max_length=DESCRIPTION_MAX_LENGTH)
    # Their own dispute photos, uploaded and ready, in their order.
    photos: list[uuid.UUID] = Field(default=[], max_length=MAX_PHOTOS)


class PhotoSize(ApiModel):
    name: str
    content_type: str
    # A link signed for five minutes: the photos are private.
    url: str
    width: int | None
    height: int | None


class DisputePhotoView(ApiModel):
    id: uuid.UUID
    captured_at: datetime | None
    sizes: list[PhotoSize]


class DisputeStudent(ApiModel):
    """The student, for ops to call."""

    name: str | None
    phone: str


class OpsDisputeItem(ApiModel):
    """A dispute in ops' queue."""

    id: uuid.UUID
    status: DisputeStatus
    reason: DisputeReason
    opened_at: datetime
    booking: str
    property: BookingPlace
    photos: int


class OpsDisputePage(ApiModel):
    # Oldest first: a queue.
    items: list[OpsDisputeItem]
    next_cursor: uuid.UUID | None


class OpsDispute(ApiModel):
    """A dispute as ops settle it: the student's words and photos, the booking, and whom to call."""

    id: uuid.UUID
    status: DisputeStatus
    reason: DisputeReason
    description: str
    opened_at: datetime
    resolved_at: datetime | None
    notes: str | None
    booking: ManagedBooking
    student: DisputeStudent
    photos: list[DisputePhotoView]


class ResolveRequest(ApiModel):
    # Refund: the bed is freed and the token refunded in full. Uphold: the stay goes ahead.
    outcome: Outcome
    # What ops found, for the record: the student and the owner get the outcome, not this.
    notes: str = Field(min_length=1, max_length=NOTES_MAX_LENGTH)
