"""Where a booking is answered (steps 5.4 and 5.6, ADRs 0048 and 0050): its owner or ops see it,
and confirm or reject it once the token is in; ops can ask a student who has moved in to say so.
Each method is one transaction.

An owner answers only their own PGs' bookings; anyone else's is a 404, as is a booking the code
doesn't find. The row is locked while it changes, so two answers at once go one after the other,
and the second finds the booking answered.
"""

from typing import TYPE_CHECKING

from app.core.errors import NotFoundError
from app.core.ids import normalize_booking_code
from app.modules.booking.domain.state_machine import BookingEvent, Party
from app.modules.booking.repository import BookingRepository
from app.modules.booking.service.transitions import Transitions
from app.modules.booking.service.views import BookingViews
from app.modules.catalog.service import CatalogLookup

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.booking.models import Booking
    from app.modules.booking.schemas import ManagedBooking


class BookingDesk:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._bookings = BookingRepository(db)
        self._catalog = CatalogLookup(db)
        self._transitions = Transitions(db, clock)
        self._views = BookingViews(db)

    async def view(self, actor: Actor, code: str, *, party: Party) -> ManagedBooking:
        async with self._db.begin():
            booking = await self._find(actor, code, party=party, lock=False)
            return await self._views.managed(booking, await self._views.place(booking))

    async def confirm(self, actor: Actor, code: str, *, party: Party) -> ManagedBooking:
        """The owner (or ops for them) takes the booking: the student hears with the address."""
        return await self._answer(actor, code, BookingEvent.CONFIRM, party=party, note=None)

    async def reject(self, actor: Actor, code: str, *, party: Party, reason: str) -> ManagedBooking:
        """The owner (or ops for them) turns it down: the bed is freed, the token refunded."""
        return await self._answer(
            actor, code, BookingEvent.REJECT, party=party, note=reason.strip()
        )

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
