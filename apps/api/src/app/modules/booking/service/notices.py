"""What a queued booking text says, when the job comes to send it (step 5.4, ADR 0048), inside
the job's transaction. Nothing when the booking has moved on since, or when that party gets no
text for that change."""

from typing import TYPE_CHECKING

from app.config import BRAND_NAME
from app.core.calendar import spoken_time
from app.modules.booking.domain.state_machine import BookingEvent, BookingStatus, Party
from app.modules.booking.repository import BookingRepository
from app.modules.booking.texts import CONFIRMED, FOR, NEW_CONFIRMED, TOKEN_IN
from app.modules.catalog.service import CatalogLookup
from app.modules.identity.service import Accounts

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession


def _day(day: date) -> str:
    """20 Aug 2027."""
    return f"{day.day} {day:%b %Y}"


class BookingNotices:
    def __init__(self, db: AsyncSession) -> None:
        self._bookings = BookingRepository(db)
        self._catalog = CatalogLookup(db)
        self._accounts = Accounts(db)

    async def message(
        self,
        booking_id: uuid.UUID,
        event: BookingEvent,
        who: Party,
        status: BookingStatus,
        *,
        instant: bool = False,
    ) -> tuple[str, str, dict[str, str]] | None:
        """The phone, the template and its blanks; None when there's nothing to send.
        ``instant``: the PG confirmed the booking itself as the token came in."""
        template = FOR.get((who, event))
        if template == TOKEN_IN and instant:
            template, status = NEW_CONFIRMED, BookingStatus.CONFIRMED
        booking = await self._bookings.by_public_id(booking_id)
        if template is None or booking is None or booking.status != status:
            return None
        place = (await self._catalog.visit_places([booking.property_id], verified_only=False))[
            booking.property_id
        ]
        if who is Party.OWNER:
            user = (await self._catalog.owner_user_ids([booking.owner_id]))[booking.owner_id]
        else:
            user = booking.student_id
        phone = (await self._accounts.many([user]))[user].phone_e164
        values = {"brand": BRAND_NAME, "pg": place.name, "code": booking.code}
        if template in {TOKEN_IN, NEW_CONFIRMED}:
            bed = await self._catalog.bed_ref(booking.bed_id)
            values |= {"room_type": bed.category_label, "move_in": _day(booking.move_in)}
        if template == TOKEN_IN:
            assert booking.confirm_by is not None  # noqa: S101 - set as the token came in
            values["confirm_by"] = spoken_time(booking.confirm_by)
        elif template == CONFIRMED:
            values |= {
                "move_in": _day(booking.move_in),
                "address": f"{place.address_line}, {place.locality}",
            }
        return phone, template, values
