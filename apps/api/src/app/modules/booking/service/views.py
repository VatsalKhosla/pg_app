"""A booking as each side sees it (ADRs 0046, 0048 to 0051): the student, and the owner or ops
who answer it. The exact address isn't here: once the booking is confirmed the student gets it by
text, and from the PG's contact, which a confirmed booking unlocks (rule 11)."""

from typing import TYPE_CHECKING, Final

from app.modules.booking.domain.disputes import DisputeReason, DisputeStatus
from app.modules.booking.domain.state_machine import BookingStatus, Party, check_in_opens_on
from app.modules.booking.schemas import BookingPlace as PlaceSchema
from app.modules.booking.schemas import (
    BookingStudent,
    CancellationTerms,
    ManagedBooking,
    RebookSearch,
    StudentBooking,
    StudentDispute,
    TimelineEntry,
)
from app.modules.catalog.domain.listing import GenderPolicy
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.catalog.service import CatalogLookup
from app.modules.identity.service import Accounts

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.booking.domain.cancellation import Cancellation
    from app.modules.booking.models import Booking, BookingEventRecord, Dispute
    from app.modules.catalog.service import BookingPlace


# Someone looking again after their booking ended searches up to a fifth above its rent: a
# filter on what they're shown, never a price.
REBOOK_BUDGET: Final = (6, 5)


class BookingViews:
    def __init__(self, db: AsyncSession) -> None:
        self._catalog = CatalogLookup(db)
        self._accounts = Accounts(db)

    async def place(self, booking: Booking) -> BookingPlace:
        """The booking's PG, whether or not the public may see it now."""
        places = await self._catalog.booking_places([booking.property_id], verified_only=False)
        return places[booking.property_id]

    async def student(
        self,
        booking: Booking,
        place: BookingPlace,
        *,
        history: Sequence[BookingEventRecord],
        cancellation: Cancellation | None,
        can_check_in: bool,
        check_window_hours: int,
        can_dispute: bool,
        dispute: Dispute | None,
        rebook_from: date | None,
    ) -> StudentBooking:
        """``rebook_from``: the month to look from for PGs like this one, when the booking ended
        through no fault of the student's; None otherwise."""
        bed = await self._catalog.bed_ref(booking.bed_id)
        status = BookingStatus(booking.status)
        return StudentBooking(
            code=booking.code,
            status=status,
            property=PlaceSchema(slug=place.slug, name=place.name, locality=place.locality),
            room_type=bed.category_label,
            move_in=booking.move_in,
            stay_months=booking.stay_months,
            planned_move_out=booking.planned_move_out,
            hold_expires_at=booking.hold_expires_at,
            confirm_by=booking.confirm_by,
            check_in_opens_on=check_in_opens_on(booking.move_in)
            if status is BookingStatus.CONFIRMED
            else None,
            can_check_in=can_check_in,
            check_window_hours=check_window_hours,
            check_window_ends_at=booking.check_window_ends_at,
            monthly_rent_paise=booking.monthly_rent_paise,
            token_paise=booking.token_paise,
            due_at_move_in_paise=booking.due_at_move_in_paise,
            deposit_paise=booking.deposit_paise,
            monthly_charges_paise=booking.monthly_charges_paise,
            one_time_charges_paise=booking.one_time_charges_paise,
            created_at=booking.created_at,
            timeline=[
                TimelineEntry(
                    event=entry.event,
                    status=BookingStatus(entry.to_status),
                    by=Party(entry.actor_type),
                    at=entry.created_at,
                )
                for entry in history
            ],
            cancellation=None
            if cancellation is None
            else CancellationTerms(refund_paise=cancellation.refund_paise, late=cancellation.late),
            can_dispute=can_dispute,
            dispute=None
            if dispute is None
            else StudentDispute(
                reason=DisputeReason(dispute.reason),
                status=DisputeStatus(dispute.status),
                opened_at=dispute.created_at,
                resolved_at=dispute.resolved_at,
            ),
            rebook=None
            if rebook_from is None
            else RebookSearch(
                locality=place.locality_slug,
                occupancy=Occupancy(bed.occupancy),
                gender=GenderPolicy(place.gender_policy),
                move_in_month=f"{rebook_from:%Y-%m}",
                budget_max_paise=booking.monthly_rent_paise * REBOOK_BUDGET[0] // REBOOK_BUDGET[1],
            ),
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
            checked_in_at=booking.checked_in_at,
            check_window_ends_at=booking.check_window_ends_at,
            # A first name is enough to greet them by; their number waits for 5.5 and 5.10.
            student=BookingStudent(name=None if student.name is None else student.name.split()[0]),
            created_at=booking.created_at,
        )
