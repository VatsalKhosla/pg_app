"""What the insights API gives (step 7.6, ADR 0063)."""

import uuid
from datetime import date, datetime

from app.core.schemas import ApiModel
from app.modules.booking.schemas import OpsBookingSummary
from app.modules.catalog.domain.listing import PropertyStatus


class RoomInsight(ApiModel):
    room_type: str
    occupancy: str
    # The room type's listed rent (rule 2's base), beside the middle of what the locality's other
    # live PGs list for the same occupancy, and how many those are.
    rent_paise: int
    locality_median_paise: int | None
    comparables: int


class PropertyInsights(ApiModel):
    property: uuid.UUID
    name: str
    # Both days in India, the last one today.
    first_day: date
    last_day: date
    # Times the PG's page was opened.
    views: int
    visit_requests: int
    # Bookings whose token came in.
    bookings: int
    # Bookings for each visit asked for, in basis points; None without visits.
    conversion_bps: int | None
    beds: int
    beds_taken: int
    taken_bps: int | None
    rooms: list[RoomInsight]


class PropertyBeds(ApiModel):
    """One of the owner's PGs today: its beds, and how many are taken (a tenant, a booking, a
    hold or a block on them)."""

    id: uuid.UUID
    name: str
    locality: str
    status: PropertyStatus
    beds: int
    beds_taken: int


class OwnerOverview(ApiModel):
    """An owner's business at a glance (ADR 0071). Rent is what the stays we placed were booked
    at (rent after the first month goes straight to the owner, so it isn't what was collected);
    fees are our invoices, GST included."""

    # Today, in India.
    today: date
    beds: int
    beds_taken: int
    properties: list[PropertyBeds]
    # Month by month, oldest first: each month's first day, the last one this month.
    months: list[date]
    # Tenants we placed who moved in during each month.
    move_ins: list[int]
    # The monthly rent of the tenants we placed who lived at the owner's PGs on any day of each
    # month.
    rent_paise: list[int]
    # Every tenant we placed, and those living there today with their monthly rent.
    tenants_placed: int
    tenants_now: int
    rent_now_paise: int
    # Every placed stay's rent for all the months it was booked for, and that less our fees.
    rent_booked_paise: int
    rent_after_fees_paise: int
    # Our placement fees invoiced, and the unpaid invoices with what's left to pay on them.
    fees_paise: int
    invoices_unpaid: int
    fees_due_paise: int
    # Bookings with the token in that wait for the owner's answer, and the soonest deadline.
    bookings_to_confirm: int
    confirm_by: datetime | None
    # Visits booked at the owner's PGs in the next seven days.
    visits_this_week: int


class ListingStatusCount(ApiModel):
    status: PropertyStatus
    count: int


class OpsInsights(ApiModel):
    """The business at a glance, for staff: each series has one number for each week, oldest first,
    and its week starts on the Monday given in ``weeks`` (India time)."""

    weeks: list[date]
    tokens_secured: list[int]
    visits_requested: list[int]
    # Placement fees invoiced to owners, before GST.
    fees_invoiced_paise: list[int]
    listings: list[ListingStatusCount]
    board: OpsBookingSummary
