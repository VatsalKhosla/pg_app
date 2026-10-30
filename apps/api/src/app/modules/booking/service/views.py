"""A booking as each side sees it (ADRs 0046, 0048): the student, and the owner or ops who answer
it. The exact address isn't here: the student gets it once the booking is confirmed (rule 11),
by text now and on their booking's page in 5.5."""

from typing import TYPE_CHECKING

from app.modules.booking.domain.state_machine import BookingStatus
from app.modules.booking.schemas import BookingPlace as PlaceSchema
from app.modules.booking.schemas import BookingStudent, ManagedBooking, StudentBooking
from app.modules.catalog.service import CatalogLookup
from app.modules.identity.service import Accounts

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.booking.models import Booking
    from app.modules.catalog.service import BookingPlace


class BookingViews:
    def __init__(self, db: AsyncSession) -> None:
        self._catalog = CatalogLookup(db)
        self._accounts = Accounts(db)

    async def place(self, booking: Booking) -> BookingPlace:
        """The booking's PG, whether or not the public may see it now."""
        places = await self._catalog.booking_places([booking.property_id], verified_only=False)
        return places[booking.property_id]

    async def student(self, booking: Booking, place: BookingPlace) -> StudentBooking:
        bed = await self._catalog.bed_ref(booking.bed_id)
        return StudentBooking(
            code=booking.code,
            status=BookingStatus(booking.status),
            property=PlaceSchema(slug=place.slug, name=place.name, locality=place.locality),
            room_type=bed.category_label,
            move_in=booking.move_in,
            stay_months=booking.stay_months,
            planned_move_out=booking.planned_move_out,
            hold_expires_at=booking.hold_expires_at,
            monthly_rent_paise=booking.monthly_rent_paise,
            token_paise=booking.token_paise,
            due_at_move_in_paise=booking.due_at_move_in_paise,
            deposit_paise=booking.deposit_paise,
            monthly_charges_paise=booking.monthly_charges_paise,
            one_time_charges_paise=booking.one_time_charges_paise,
            created_at=booking.created_at,
        )

    async def managed(self, booking: Booking, place: BookingPlace) -> ManagedBooking:
        bed = await self._catalog.bed_ref(booking.bed_id)
        student = (await self._accounts.many([booking.student_id]))[booking.student_id]
        return ManagedBooking(
            code=booking.code,
            status=BookingStatus(booking.status),
            property=PlaceSchema(slug=place.slug, name=place.name, locality=place.locality),
            room_type=bed.category_label,
            room=bed.room_label,
            bed=bed.label,
            move_in=booking.move_in,
            stay_months=booking.stay_months,
            planned_move_out=booking.planned_move_out,
            monthly_rent_paise=booking.monthly_rent_paise,
            token_paise=booking.token_paise,
            due_at_move_in_paise=booking.due_at_move_in_paise,
            deposit_paise=booking.deposit_paise,
            hold_expires_at=booking.hold_expires_at,
            confirm_by=booking.confirm_by,
            # A first name is enough to greet them by; their number waits for 5.5 and 5.10.
            student=BookingStudent(name=None if student.name is None else student.name.split()[0]),
            created_at=booking.created_at,
        )
