"""An owner's numbers for one PG (step 7.6, ADR 0063): page views, visits asked for, bookings
made, how full it is today, and each room's rent beside its locality's. Each comes from its own
module's service; this module only puts them side by side."""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from app.core.calendar import india_date, india_start
from app.core.errors import NotFoundError
from app.modules.booking.service import (
    BookingBoard,
    bookings_made,
    placed_stays,
    waiting_for_owner,
)
from app.modules.booking.service.stats import secured_by_week
from app.modules.catalog.domain.listing import PropertyStatus
from app.modules.catalog.service import CatalogLookup
from app.modules.catalog.service.owner_area import ListingViews
from app.modules.insights.domain.insights import conversion_bps, series, taken_bps, week_starts
from app.modules.insights.domain.owner import (
    Stay,
    booked_rent,
    living_on,
    month_starts,
    move_ins_by_month,
    rent_by_month,
)
from app.modules.insights.schemas import (
    ListingStatusCount,
    OpsInsights,
    OwnerOverview,
    PropertyBeds,
    PropertyInsights,
    RoomInsight,
)
from app.modules.inventory.service import AllocationService, AvailabilityLookup
from app.modules.invoices.service import fee_totals, fees_by_week
from app.modules.visits.service import VisitLookup

if TYPE_CHECKING:
    import uuid
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.pricing.service import QuoteService


@dataclass(frozen=True, slots=True)
class _Counts:
    name: str
    views: int
    visits: int
    bookings: int


class OwnerInsights:
    def __init__(self, db: AsyncSession, clock: Clock, quotes: QuoteService) -> None:
        self._db = db
        self._clock = clock
        self._quotes = quotes

    async def of(self, actor: Actor, property_id: uuid.UUID, *, days: int) -> PropertyInsights:
        """The last ``days`` days, today included, for the owner's own PG; anyone else's is a
        404."""
        now = self._clock.now()
        last = india_date(now)
        first = last - timedelta(days=days - 1)
        counts = await self._counts(actor, property_id, first, now)
        today = await AllocationService(self._db, self._clock).window(
            property_id, start=last, days=1, owner=actor.user_id
        )
        beds = sum(len(item.category.active_beds) for item in today.categories)
        free = sum(item.free_beds for item in today.categories)
        market = await self._quotes.market(property_id)
        return PropertyInsights(
            property=property_id,
            name=counts.name,
            first_day=first,
            last_day=last,
            views=counts.views,
            visit_requests=counts.visits,
            bookings=counts.bookings,
            conversion_bps=conversion_bps(counts.bookings, counts.visits),
            beds=beds,
            beds_taken=beds - free,
            taken_bps=taken_bps(beds - free, beds),
            rooms=[
                RoomInsight(
                    room_type=room.category.label,
                    occupancy=room.category.occupancy,
                    rent_paise=room.category.base_rent,
                    locality_median_paise=room.median_rent,
                    comparables=room.comparables,
                )
                for room in market.rooms
            ],
        )

    async def _counts(
        self, actor: Actor, property_id: uuid.UUID, first: date, now: datetime
    ) -> _Counts:
        async with self._db.begin():
            owned = await CatalogLookup(self._db).owned_property(actor.user_id, property_id)
            if owned is None:
                raise NotFoundError
            # Whole days in India, today's included to its end.
            last = india_date(now)
            start, end = india_start(first), india_start(last + timedelta(days=1))
            return _Counts(
                name=owned.name,
                views=await ListingViews(self._db, self._clock).between(owned.id, first, last),
                visits=await VisitLookup(self._db).requested_at(owned.id, start, end),
                bookings=await bookings_made(self._db, owned.id, start, end),
            )


# How far ahead the overview counts the visits booked.
VISITS_AHEAD: Final = timedelta(days=7)


class OwnerOverviewService:
    """An owner's whole business at a glance (ADR 0071): each module counts its own rows for the
    owner, and this lines them up. An owner without an owner record yet sees empty numbers."""

    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    async def of(self, actor: Actor, *, months: int) -> OwnerOverview:
        now = self._clock.now()
        today = india_date(now)
        firsts = month_starts(today, months)
        catalog = CatalogLookup(self._db)
        async with self._db.begin():
            owner_id = await catalog.owner_id_of_user(actor.user_id)
            owned = await catalog.owned_properties(actor.user_id)
            beds = AvailabilityLookup(self._db)
            counts = [await beds.beds_on(row.id, today) for row in owned]
            rows = [] if owner_id is None else await placed_stays(self._db, owner_id)
            fees = None if owner_id is None else await fee_totals(self._db, owner_id)
            waiting = None if owner_id is None else await waiting_for_owner(self._db, owner_id)
            visits = await VisitLookup(self._db).booked_between(
                [row.id for row in owned], now, now + VISITS_AHEAD
            )
        stays = [
            Stay(
                move_in=row.move_in,
                ends=row.ends,
                monthly_rent_paise=row.monthly_rent_paise,
                stay_months=row.stay_months,
            )
            for row in rows
        ]
        living = living_on(stays, today)
        booked = booked_rent(stays)
        fees_paise = 0 if fees is None else fees.invoiced_paise
        return OwnerOverview(
            today=today,
            beds=sum(total for total, _ in counts),
            beds_taken=sum(total - free for total, free in counts),
            properties=[
                PropertyBeds(
                    id=row.public_id,
                    name=row.name,
                    locality=row.locality,
                    status=PropertyStatus(row.status),
                    beds=total,
                    beds_taken=total - free,
                )
                for row, (total, free) in zip(owned, counts, strict=True)
            ],
            months=firsts,
            move_ins=move_ins_by_month(stays, firsts),
            rent_paise=rent_by_month(stays, firsts),
            tenants_placed=len(stays),
            tenants_now=len(living),
            rent_now_paise=sum(stay.monthly_rent_paise for stay in living),
            rent_booked_paise=booked,
            rent_after_fees_paise=booked - fees_paise,
            fees_paise=fees_paise,
            invoices_unpaid=0 if fees is None else fees.unpaid,
            fees_due_paise=0 if fees is None else fees.due_paise,
            bookings_to_confirm=0 if waiting is None else waiting.count,
            confirm_by=None if waiting is None else waiting.soonest,
            visits_this_week=visits,
        )


class OpsDashboard:
    """The whole business, week by week, for staff (the staff dashboard): each module counts its own
    rows, and this only lines the weeks up."""

    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    async def of(self, *, weeks: int) -> OpsInsights:
        now = self._clock.now()
        mondays = week_starts(india_date(now), weeks)
        start, end = india_start(mondays[0]), india_start(india_date(now) + timedelta(days=1))
        async with self._db.begin():
            tokens = await secured_by_week(self._db, start, end)
            visits = await VisitLookup(self._db).requested_by_week(start, end)
            fees = await fees_by_week(self._db, start, end)
            listings = await CatalogLookup(self._db).status_counts()
        board = await BookingBoard(self._db, self._clock).summary()
        return OpsInsights(
            weeks=mondays,
            tokens_secured=series(mondays, tokens),
            visits_requested=series(mondays, visits),
            fees_invoiced_paise=series(mondays, fees),
            listings=[
                ListingStatusCount(status=PropertyStatus(status), count=count)
                for status, count in sorted(listings.items())
            ],
            board=board,
        )
