"""The bookings API's shapes (ARCHITECTURE §15; ADR 0046)."""

import uuid
from datetime import date, datetime
from typing import Final

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.booking.domain.state_machine import BookingStatus

REASON_MAX_LENGTH: Final = 500


class HoldRequest(ApiModel):
    # The student's own quote, unexpired: the booking copies its money.
    quote: uuid.UUID


class BookingPlace(ApiModel):
    slug: str
    name: str
    locality: str


class StudentBooking(ApiModel):
    """A booking as its student sees it: the quote's money, fixed for the stay (rule 5). The
    exact address shows once the owner confirms (rule 11)."""

    code: str
    status: BookingStatus
    property: BookingPlace
    room_type: str
    move_in: date
    stay_months: int
    planned_move_out: date
    # While HELD, the token must be paid by then: the one countdown the student sees.
    hold_expires_at: datetime
    monthly_rent_paise: int
    token_paise: int
    due_at_move_in_paise: int
    deposit_paise: int
    monthly_charges_paise: int
    one_time_charges_paise: int
    created_at: datetime


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
    student: BookingStudent
    created_at: datetime


class RejectRequest(ApiModel):
    # Why, for the student's record and ops; never shown to other students.
    reason: str = Field(min_length=1, max_length=REASON_MAX_LENGTH)
