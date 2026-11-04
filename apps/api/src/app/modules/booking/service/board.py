"""The bookings board (step 5.10, ADR 0054): what ops read to run a day of bookings without the
database. Each method is one read-only transaction; what ops do goes through BookingDesk and
Disputes, and so through the state machine.

The list finds bookings by status, channel or whether they need a person now, and by a search:
a booking code, a student's phone or part of a PG's name. Its queries don't grow with the page.
A booking's own page says whom to call, what it's waiting for, what the state machine would take
from ops now, and everything that happened, with who did it and why.
"""

from dataclasses import replace
from typing import TYPE_CHECKING, Final

from app.core.calendar import india_date
from app.core.errors import NotFoundError
from app.core.ids import normalize_booking_code
from app.core.pagination import split_page
from app.modules.booking.domain.board import needs_attention, ops_actions, timer_of
from app.modules.booking.domain.disputes import DisputeReason, DisputeStatus
from app.modules.booking.domain.state_machine import BookingStatus, Moment, Party
from app.modules.booking.models import Channel
from app.modules.booking.repository import BoardFilter, BookingRepository, DisputeRepository
from app.modules.booking.schemas import (
    BoardTimerView,
    BookingContact,
    BookingDisputeRef,
    BookingHistoryEntry,
    BookingStudent,
    OpsBooking,
    OpsBookingItem,
    OpsBookingSummary,
    StatusCount,
)
from app.modules.booking.schemas import BookingPlace as PlaceSchema
from app.modules.booking.service.transitions import facts_of
from app.modules.booking.service.views import BookingViews
from app.modules.catalog.service import CatalogLookup
from app.modules.identity.domain.phones import normalize_indian_mobile
from app.modules.identity.service import Accounts
from app.modules.pricing.service import BookingTerms
from app.modules.visits.service import VisitLookup

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.core.pagination import PageRequest
    from app.modules.booking.domain.board import BoardTimer
    from app.modules.booking.models import Booking, Dispute

# A search by a PG's name looks through this many PGs at most.
NAMED_PGS: Final = 50


def _timer_view(timer: BoardTimer | None, now: datetime) -> BoardTimerView | None:
    if timer is None:
        return None
    return BoardTimerView(kind=timer.kind, since=timer.since, due=timer.due, late=timer.late(now))


def _timer(booking: Booking, dispute: Dispute | None, now: datetime) -> BoardTimer | None:
    return timer_of(
        BookingStatus(booking.status),
        token_secured_at=booking.token_secured_at,
        disputed_at=None if dispute is None else dispute.opened_at,
        move_in=booking.move_in,
        now=now,
    )


def _first_name(name: str | None) -> str | None:
    return None if name is None else name.split()[0]


class BookingBoard:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._bookings = BookingRepository(db)
        self._disputes = DisputeRepository(db)
        self._catalog = CatalogLookup(db)
        self._accounts = Accounts(db)
        self._terms = BookingTerms(db)
        self._views = BookingViews(db)
        self._visits = VisitLookup(db)

    async def page(
        self,
        request: PageRequest,
        *,
        status: BookingStatus | None,
        channel: Channel | None,
        attention: bool,
        search: str | None,
    ) -> tuple[list[OpsBookingItem], uuid.UUID | None]:
        now = self._clock.now()
        async with self._db.begin():
            found = await self._filter(status, channel, attention, search, now=now)
            rows = await self._bookings.board(found, after=request.after, limit=request.limit)
            items, next_cursor = split_page(rows, request, cursor_of=lambda row: row.public_id)
            places = await self._catalog.booking_places(
                {booking.property_id for booking in items}, verified_only=False
            )
            labels = await self._catalog.category_labels(
                {booking.room_category_id for booking in items}
            )
            people = await self._accounts.many({booking.student_id for booking in items})
            disputes = await self._disputes.of_bookings({booking.id for booking in items})
        views = []
        for booking in items:
            place = places[booking.property_id]
            timer = _timer(booking, disputes.get(booking.id), now)
            views.append(
                OpsBookingItem(
                    code=booking.code,
                    status=BookingStatus(booking.status),
                    channel=Channel(booking.channel),
                    property=PlaceSchema(slug=place.slug, name=place.name, locality=place.locality),
                    room_type=labels[booking.room_category_id],
                    move_in=booking.move_in,
                    student=BookingStudent(name=_first_name(people[booking.student_id].name)),
                    created_at=booking.created_at,
                    timer=_timer_view(timer, now),
                    attention=needs_attention(timer, now),
                )
            )
        return views, next_cursor

    async def summary(self) -> OpsBookingSummary:
        now = self._clock.now()
        async with self._db.begin():
            counts = await self._bookings.board_counts(now=now, today=india_date(now))
        return OpsBookingSummary(
            statuses=[
                StatusCount(status=status, count=counts.by_status.get(status, 0))
                for status in BookingStatus
            ],
            attention=counts.unconfirmed_late + counts.disputes + counts.move_ins,
            unconfirmed_late=counts.unconfirmed_late,
            disputes_open=counts.disputes,
            move_ins_due=counts.move_ins,
        )

    async def booking(self, code: str) -> OpsBooking:
        now = self._clock.now()
        canonical = normalize_booking_code(code)
        async with self._db.begin():
            booking = None if canonical is None else await self._bookings.by_code(canonical)
            if booking is None:
                raise NotFoundError
            return await self._view(booking, now)

    async def _view(self, booking: Booking, now: datetime) -> OpsBooking:
        place = await self._views.place(booking)
        managed = await self._views.managed(booking, place)
        terms = await self._terms.of(booking.booking_policy_id)
        dispute = (await self._disputes.of_bookings([booking.id])).get(booking.id)
        history = (await self._bookings.events_of([booking.id])).get(booking.id, [])
        owner_user = (await self._catalog.owner_user_ids([booking.owner_id]))[booking.owner_id]
        people = await self._accounts.many(
            {
                booking.student_id,
                owner_user,
                *(entry.actor_id for entry in history if entry.actor_id is not None),
            }
        )
        student, owner = people[booking.student_id], people[owner_user]
        timer = _timer(booking, dispute, now)
        return OpsBooking(
            **managed.model_dump(),
            student_contact=BookingContact(name=student.name, phone=student.phone_e164),
            owner_contact=BookingContact(name=owner.name, phone=owner.phone_e164),
            owner_cancellations=await self._bookings.owner_cancellations(booking.owner_id),
            monthly_charges_paise=booking.monthly_charges_paise,
            one_time_charges_paise=booking.one_time_charges_paise,
            fee_paise=booking.fee_paise,
            gst_paise=booking.gst_paise,
            owner_fee_total_paise=booking.owner_fee_total_paise,
            moved_out_on=booking.moved_out_on,
            cancelled_at=booking.cancelled_at,
            cancellation_kind=booking.cancellation_kind,
            timer=_timer_view(timer, now),
            attention=needs_attention(timer, now),
            actions=ops_actions(facts_of(booking, place), Moment(now), terms),
            dispute=None
            if dispute is None
            else BookingDisputeRef(
                id=dispute.public_id,
                status=DisputeStatus(dispute.status),
                reason=DisputeReason(dispute.reason),
            ),
            visit=None
            if booking.visit_id is None
            else await self._visits.public_id(booking.visit_id),
            history=[
                BookingHistoryEntry(
                    event=entry.event,
                    from_status=None
                    if entry.from_status is None
                    else BookingStatus(entry.from_status),
                    to_status=BookingStatus(entry.to_status),
                    by=Party(entry.actor_type),
                    by_name=None if entry.actor_id is None else people[entry.actor_id].name,
                    note=entry.payload.get("note"),
                    at=entry.created_at,
                )
                for entry in history
            ],
        )

    async def _filter(
        self,
        status: BookingStatus | None,
        channel: Channel | None,
        attention: bool,
        search: str | None,
        *,
        now: datetime,
    ) -> BoardFilter:
        found = BoardFilter(
            status=status,
            channel=channel,
            attention_at=(now, india_date(now)) if attention else None,
        )
        if search is None:
            return found
        return await self._searched(found, search.strip())

    async def _searched(self, found: BoardFilter, search: str) -> BoardFilter:
        """A search means what it looks like: a booking's code, a student's phone, or else part
        of a PG's name. A phone nobody has finds nothing."""
        code = normalize_booking_code(search)
        if code is not None:
            return replace(found, code=code)
        phone = normalize_indian_mobile(search)
        if phone is None:
            named = await self._catalog.property_ids_named(search, limit=NAMED_PGS)
            return replace(found, property_ids=named)
        student = await self._accounts.find(phone)
        return (
            replace(found, property_ids=[])
            if student is None
            else replace(found, student_id=student.id)
        )
