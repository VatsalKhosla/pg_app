"""Where a booking is answered (steps 5.4, 5.6 and 5.10, ADRs 0048, 0050 and 0054): its owner or
ops see it, and confirm or reject it once the token is in; ops can ask a student who has moved in
to say so, cancel for an owner who can't take the booking after all, and record a move-out. Each
method is one transaction, and ops give a reason for each change, kept in the booking's history.

An owner answers only their own PGs' bookings; anyone else's is a 404, as is a booking the code
doesn't find. The row is locked while it changes, so two answers at once go one after the other,
and the second finds the booking answered.
"""

from typing import TYPE_CHECKING

from app.core.errors import NotFoundError
from app.core.ids import normalize_booking_code
from app.core.pagination import split_page
from app.modules.booking.domain.state_machine import BookingEvent, Moment, Party
from app.modules.booking.repository import BookingRepository
from app.modules.booking.schemas import BookingPlace, OwnerBookingItem
from app.modules.booking.service.transitions import Transitions
from app.modules.booking.service.views import BookingViews
from app.modules.catalog.service import CatalogLookup

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.pagination import PageRequest
    from app.modules.booking.domain.state_machine import BookingStatus
    from app.modules.booking.models import Booking
    from app.modules.booking.schemas import ManagedBooking


class BookingDesk:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._bookings = BookingRepository(db)
        self._catalog = CatalogLookup(db)
        self._transitions = Transitions(db, clock)
        self._views = BookingViews(db)

    async def view(self, actor: Actor, code: str, *, party: Party) -> ManagedBooking:
        async with self._db.begin():
            booking = await self._find(actor, code, party=party, lock=False)
            return await self._views.managed(booking, await self._views.place(booking))

    async def inbox(
        self, actor: Actor, request: PageRequest, *, status: BookingStatus | None
    ) -> tuple[list[OwnerBookingItem], uuid.UUID | None]:
        """The owner's bookings at all their PGs, newest first, of one status if asked (step
        7.3). The same few queries, however long the page."""
        async with self._db.begin():
            owner = await self._catalog.owner_id_of_user(actor.user_id)
            if owner is None:
                return [], None
            found = await self._bookings.owner_page(
                owner,
                statuses=None if status is None else [status],
                after=request.after,
                limit=request.limit,
            )
            items, next_cursor = split_page(found, request, cursor_of=lambda row: row.public_id)
            places = await self._catalog.booking_places(
                {row.property_id for row in items}, verified_only=False
            )
            labels = await self._catalog.category_labels({row.room_category_id for row in items})
        return [
            OwnerBookingItem(
                code=row.code,
                status=row.status,  # type: ignore[arg-type]
                property=BookingPlace(
                    slug=places[row.property_id].slug,
                    name=places[row.property_id].name,
                    locality=places[row.property_id].locality,
                ),
                room_type=labels[row.room_category_id],
                move_in=row.move_in,
                stay_months=row.stay_months,
                monthly_rent_paise=row.monthly_rent_paise,
                confirm_by=row.confirm_by,
                created_at=row.created_at,
            )
            for row in items
        ], next_cursor

    async def confirm(
        self, actor: Actor, code: str, *, party: Party, reason: str | None = None
    ) -> ManagedBooking:
        """The owner (or ops for them, saying why) takes the booking: the student hears with the
        address."""
        note = None if reason is None else reason.strip()
        return await self._answer(actor, code, BookingEvent.CONFIRM, party=party, note=note)

    async def reject(self, actor: Actor, code: str, *, party: Party, reason: str) -> ManagedBooking:
        """The owner (or ops for them) turns it down: the bed is freed, the token refunded."""
        return await self._answer(
            actor, code, BookingEvent.REJECT, party=party, note=reason.strip()
        )

    async def owner_cancel(self, actor: Actor, code: str, *, reason: str) -> ManagedBooking:
        """Ops, for an owner who can't take the booking after all: the bed is freed, the token
        refunded in full, and the student told and shown PGs like it. The owner's count of
        cancellations on the board goes up."""
        return await self._answer(
            actor, code, BookingEvent.OWNER_CANCEL, party=Party.OPS, note=reason.strip()
        )

    async def move_out(
        self, actor: Actor, code: str, *, moved_out_on: date, reason: str
    ) -> ManagedBooking:
        """Ops record that the student has left: the booking is over and the bed free from that
        day. The day must be after the move-in and not still to come."""
        async with self._db.begin():
            booking = await self._find(actor, code, party=Party.OPS, lock=True)
            place = await self._views.place(booking)
            await self._transitions.apply(
                booking,
                BookingEvent.MOVE_OUT,
                Party.OPS,
                place,
                by=actor.user_id,
                moment=Moment(self._clock.now(), moved_out_on=moved_out_on),
                note=reason.strip(),
            )
            return await self._views.managed(booking, place)

    async def move_in_reminder(self, actor: Actor, code: str) -> bool:
        """Ops heard the student has moved in: the student is asked to say so themselves. Whether
        the text went now; once a day at most."""
        async with self._db.begin():
            booking = await self._find(actor, code, party=Party.OPS, lock=False)
            place = await self._views.place(booking)
            return await self._transitions.remind_to_check_in(booking, place, by=actor.user_id)

    async def _answer(
        self, actor: Actor, code: str, event: BookingEvent, *, party: Party, note: str | None
    ) -> ManagedBooking:
        async with self._db.begin():
            booking = await self._find(actor, code, party=party, lock=True)
            place = await self._views.place(booking)
            await self._transitions.apply(booking, event, party, place, by=actor.user_id, note=note)
            return await self._views.managed(booking, place)

    async def _find(self, actor: Actor, code: str, *, party: Party, lock: bool) -> Booking:
        canonical = normalize_booking_code(code)
        booking = None if canonical is None else await self._bookings.by_code(canonical, lock=lock)
        if booking is None:
            raise NotFoundError
        if party is Party.OWNER:
            owner = await self._catalog.owner_id_of_user(actor.user_id)
            if owner is None or owner != booking.owner_id:
                raise NotFoundError
        return booking
