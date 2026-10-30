"""The bookings API's shapes (ARCHITECTURE §15; ADR 0046)."""

import uuid
from datetime import date, datetime

from app.core.schemas import ApiModel
from app.modules.booking.domain.state_machine import BookingStatus


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
