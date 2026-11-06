"""What the insights API gives (step 7.6, ADR 0063)."""

import uuid
from datetime import date

from app.core.schemas import ApiModel


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
