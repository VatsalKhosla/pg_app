"""Quotes (ARCHITECTURE §8.4; step 4.4, ADR 0039); each method is one transaction.

A quote prices one room category of a PG the public may see, for a move-in and a stay: the
policies in force, the PG's active rule set, the band for its locality and occupancy, and how full
the category is that day go into the engine, and the answer is stored with all of them, its
explanation, and the category's deposit and charges as they stood. It stands for 30 minutes; a
booking (Phase 5) takes only one that hasn't expired, and copies its money.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import structlog

from app.core.calendar import india_date
from app.core.errors import NotFoundError
from app.core.flags import Flag
from app.modules.catalog.domain.charges import (
    MandatoryCharge,
    MeteredCharge,
    MonthlyCharge,
    OneTimeCharge,
    monthly_total,
    one_time_total,
)
from app.modules.catalog.service import CatalogLookup, PricedCategory, PricedProperty
from app.modules.geo.service import GeoLookup
from app.modules.inventory.service import AvailabilityLookup
from app.modules.pricing.domain.engine import ImpossibleBoundsError, quote
from app.modules.pricing.domain.quotes import (
    PREVIEW_DAYS,
    QUOTE_TTL,
    bookable_from,
    explanation,
    inputs_digest,
    median_rent,
    preview_problems,
    quote_problems,
)
from app.modules.pricing.errors import PricingConfigError, QuoteExpiredError, QuoteInvalidError
from app.modules.pricing.models import (
    PriceQuote,
    PricingCapsVersion,
)
from app.modules.pricing.repository import (
    PolicyRepository,
    QuoteRepository,
    RentBandRepository,
    RuleSetRepository,
)
from app.modules.pricing.service.inputs import PgPricing, PricingInputs
from app.modules.pricing.service.policies import pricing_caps

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.flags import FlagReader
    from app.core.money import Paise
    from app.modules.pricing.domain.engine import ClampKind, Quote
    from app.modules.pricing.domain.policies import PricingCaps
    from app.modules.pricing.models import PricingRuleSet
    from app.modules.pricing.models import RentBand as RentBandRow
    from app.modules.pricing.occupancy import BedsTaken

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CalendarWeek:
    move_in: date
    monthly_rent_paise: Paise
    # The limits that held this week's rent back; the editor's chart marks them.
    clamps: tuple[ClampKind, ...] = ()


@dataclass(frozen=True, slots=True)
class CalendarRoom:
    category: PricedCategory
    # Empty when the room can't be priced (ops have been told).
    weeks: tuple[CalendarWeek, ...]
    # Beds free for a whole stay from the first move-in shown, from real inventory: active
    # beds that no booking, offline tenant or maintenance holds then (ADR 0044).
    beds_free: int


@dataclass(frozen=True, slots=True)
class CalendarView:
    property: PricedProperty
    stay_months: int
    rooms: tuple[CalendarRoom, ...]


@dataclass(frozen=True, slots=True)
class PreviewView:
    quote: Quote
    explanation: str
    category: PricedCategory
    # The category's charges as a quote keeps them, and their totals.
    charges: list[dict[str, object]]
    monthly_charges: Paise
    one_time_charges: Paise
    # The first day students can quote this move-in; None when they can now.
    bookable_from: date | None


@dataclass(frozen=True, slots=True)
class MarketRoom:
    category: PricedCategory
    band: RentBandRow | None
    # The middle of other published PGs' listed rents for the occupancy there; None for none.
    median_rent: Paise | None
    comparables: int


@dataclass(frozen=True, slots=True)
class MarketView:
    property: PricedProperty
    locality: str
    caps: PricingCaps
    rooms: tuple[MarketRoom, ...]


@dataclass(frozen=True, slots=True)
class QuoteView:
    row: PriceQuote
    property: PricedProperty
    category: PricedCategory
    expired: bool


def _charge(charge: MandatoryCharge) -> dict[str, object]:
    """A charge as the quote keeps it: what the student was shown."""
    match charge:
        case MonthlyCharge():
            return {
                "type": "monthly",
                "kind": charge.kind,
                "label": charge.label,
                "amount_paise": charge.amount,
            }
        case MeteredCharge():
            return {
                "type": "metered",
                "kind": charge.kind,
                "label": charge.label,
                "rate_paise": charge.rate,
                "unit": charge.unit,
                "monthly_estimate_paise": charge.monthly_estimate,
            }
        case OneTimeCharge():
            return {
                "type": "oneTime",
                "kind": charge.kind,
                "label": charge.label,
                "amount_paise": charge.amount,
            }


class QuoteService:
    def __init__(
        self, db: AsyncSession, clock: Clock, *, flags: FlagReader, beds: BedsTaken
    ) -> None:
        self._db = db
        self._clock = clock
        self._flags = flags
        self._inputs = PricingInputs(db, beds=beds)
        self._catalog = CatalogLookup(db)
        self._availability = AvailabilityLookup(db)
        self._geo = GeoLookup(db)
        self._policies = PolicyRepository(db)
        self._sets = RuleSetRepository(db)
        self._bands = RentBandRepository(db)
        self._quotes = QuoteRepository(db)

    async def create(
        self, actor: Actor | None, category_id: uuid.UUID, *, move_in: date, stay_months: int
    ) -> QuoteView:
        verified_only = await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        now = self._clock.now()
        today = india_date(now)
        async with self._db.begin():
            found = await self._catalog.priced_category(category_id, verified_only=verified_only)
            if found is None or not found[0].public or not found[1].active:
                raise NotFoundError
            place, category = found
            pricing = await self._inputs.active(place, now=now)
            if problems := quote_problems(
                move_in=move_in, stay_months=stay_months, today=today, booking=pricing.booking
            ):
                raise QuoteInvalidError(problems)
            band_row = pricing.bands.get(category.occupancy)
            context = await self._inputs.context(pricing, category, move_in, stay_months, today)
            try:
                result = quote(context)
            except ImpossibleBoundsError as error:
                # Ops' to fix (the owner's bounds against the band); nothing is quoted meanwhile.
                logger.error("no rent the bounds allow", property=str(place.public_id))
                msg = "This room can't be priced right now; our team has been told."
                raise PricingConfigError(msg) from error
            rule_set = pricing.rule_set
            fee_row, booking_row, caps_row = pricing.fee_row, pricing.booking_row, pricing.caps_row
            versions = {
                "rule_set": None if rule_set is None else rule_set.id,
                "fee_policy": fee_row.id,
                "booking_policy": booking_row.id,
                "pricing_caps": caps_row.id,
                "rent_band": None if band_row is None else band_row.id,
                "engine": result.engine_version,
            }
            row = PriceQuote(
                user_id=None if actor is None else actor.user_id,
                property_id=place.id,
                room_category_id=category.id,
                move_in=move_in,
                stay_months=stay_months,
                quoted_on=today,
                occupancy_bps=context.occupancy_bps,
                base_rent_paise=result.base_rent_paise,
                monthly_rent_paise=result.monthly_rent_paise,
                premium_bps=result.premium_bps,
                discount_bps=result.discount_bps,
                adjustments=[
                    {
                        "kind": item.kind,
                        "label": item.label,
                        "bps": item.bps,
                        "rent_paise": item.rent_paise,
                    }
                    for item in result.adjustments
                ],
                clamps=[
                    {"kind": item.kind, "asked": item.asked, "allowed": item.allowed}
                    for item in result.clamps
                ],
                fee_paise=result.fee_paise,
                gst_paise=result.gst_paise,
                owner_fee_total_paise=result.owner_fee_total_paise,
                token_paise=result.token_paise,
                due_at_move_in_paise=result.due_at_move_in_paise,
                deposit_paise=category.security_deposit,
                mandatory_charges=[_charge(charge) for charge in category.charges],
                monthly_charges_paise=monthly_total(category.charges),
                one_time_charges_paise=one_time_total(category.charges),
                explanation=explanation(result),
                rule_set_id=None if rule_set is None else rule_set.id,
                fee_policy_id=fee_row.id,
                booking_policy_id=booking_row.id,
                pricing_caps_id=caps_row.id,
                rent_band_id=None if band_row is None else band_row.id,
                engine_version=result.engine_version,
                inputs_sha256=inputs_digest(context, versions=versions),
                expires_at=now + QUOTE_TTL,
            )
            self._quotes.add(row)
            await self._db.flush()
            return QuoteView(row, place, category, expired=False)

    async def calendar(
        self, slug: str, *, start: date | None, weeks: int, stay_months: int
    ) -> CalendarView:
        """What each room of a PG the public may see costs a month for a move-in each week from
        ``start`` (today at the earliest) for ``weeks`` weeks, up to the booking horizon, as a
        quote would say (§8.5), with each room's beds free."""
        verified_only = await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        now = self._clock.now()
        today = india_date(now)
        async with self._db.begin():
            place = await self._catalog.priced_property_by_slug(slug, verified_only=verified_only)
            if place is None or not place.public:
                raise NotFoundError
            pricing = await self._inputs.active(place, now=now)
            first = max(start or today, today)
            horizon = today + timedelta(days=pricing.booking.max_advance_days)
            move_ins = [
                day
                for day in (first + timedelta(weeks=week) for week in range(weeks))
                if day <= horizon
            ]
            beds = await self._catalog.beds(place.id)
            free = await self._free_for(place, move_ins, stay_months)
            rooms = []
            for category in place.categories:
                if not category.active or beds.get(category.id, 0) == 0:
                    continue
                prices = await self._weeks(pricing, category, move_ins, stay_months, today)
                if prices is None:
                    logger.error("no rent the bounds allow", property=str(place.public_id))
                rooms.append(CalendarRoom(category, prices or (), free.get(category.id, 0)))
            return CalendarView(place, stay_months, tuple(rooms))

    # Ops' pricing editor (ARCHITECTURE §8.6; step 4.6, ADR 0041): any version's prices, before
    # it's in force, from the same inputs and engine as a quote.

    async def preview(
        self, rule_set_id: uuid.UUID, category_id: uuid.UUID, *, move_in: date, stay_months: int
    ) -> PreviewView:
        """What a quote made today for this room, move-in and stay would say were
        ``rule_set_id`` in force, of any status, the owner's fee included. Nothing is stored."""
        now = self._clock.now()
        today = india_date(now)
        async with self._db.begin():
            rule_set, place = await self._set_and_place(rule_set_id)
            category = next(
                (
                    item
                    for item in place.categories
                    if item.public_id == category_id and item.active
                ),
                None,
            )
            if category is None:
                raise NotFoundError
            if problems := preview_problems(move_in=move_in, stay_months=stay_months, today=today):
                raise QuoteInvalidError(problems)
            pricing = await self._inputs.of(place, now=now, rule_set=rule_set)
            context = await self._inputs.context(pricing, category, move_in, stay_months, today)
            try:
                result = quote(context)
            except ImpossibleBoundsError as error:
                msg = f"{category.label} has no rent its bounds allow: {error}"
                raise QuoteInvalidError([msg]) from error
            return PreviewView(
                quote=result,
                explanation=explanation(result),
                category=category,
                charges=[_charge(charge) for charge in category.charges],
                monthly_charges=monthly_total(category.charges),
                one_time_charges=one_time_total(category.charges),
                bookable_from=bookable_from(move_in, today=today, booking=pricing.booking),
            )

    async def set_calendar(
        self, rule_set_id: uuid.UUID, *, start: date | None, weeks: int, stay_months: int
    ) -> CalendarView:
        """Each active room's rent for a move-in each week from ``start`` (today at the
        earliest), for ``weeks`` weeks up to a year ahead, were ``rule_set_id`` in force: the
        editor's price chart."""
        now = self._clock.now()
        today = india_date(now)
        async with self._db.begin():
            rule_set, place = await self._set_and_place(rule_set_id)
            pricing = await self._inputs.of(place, now=now, rule_set=rule_set)
            first = max(start or today, today)
            last = today + timedelta(days=PREVIEW_DAYS)
            move_ins = [
                day
                for day in (first + timedelta(weeks=week) for week in range(weeks))
                if day <= last
            ]
            free = await self._free_for(place, move_ins, stay_months)
            rooms = [
                CalendarRoom(
                    category,
                    await self._weeks(pricing, category, move_ins, stay_months, today) or (),
                    free.get(category.id, 0),
                )
                for category in place.categories
                if category.active
            ]
            return CalendarView(place, stay_months, tuple(rooms))

    async def _free_for(
        self, place: PricedProperty, move_ins: list[date], stay_months: int
    ) -> dict[int, int]:
        """Each room's beds free for a whole stay from the first move-in shown (none: none)."""
        if not move_ins:
            return {}
        return await self._availability.free_beds_for_stay(place.id, move_ins[0], stay_months)

    async def market(self, property_id: uuid.UUID) -> MarketView:
        """Beside each of the PG's active rooms: the band in force for its locality and
        occupancy, and the middle of the rents other published PGs there list for that
        occupancy (§8.6); and the caps in force."""
        now = self._clock.now()
        async with self._db.begin():
            place = await self._catalog.priced_property(property_id)
            if place is None:
                raise NotFoundError
            caps_row = await self._policies.in_force(PricingCapsVersion, at=now)
            if caps_row is None:
                raise PricingConfigError
            locality = (await self._geo.localities([place.locality_id]))[place.locality_id]
            rooms = []
            for category in place.categories:
                if not category.active:
                    continue
                band = await self._bands.in_force(place.locality_id, category.occupancy, at=now)
                rents = await self._catalog.locality_rents(
                    place.locality_id, category.occupancy, except_property=place.id
                )
                rooms.append(MarketRoom(category, band, median_rent(rents), len(rents)))
            return MarketView(place, locality.name, pricing_caps(caps_row), tuple(rooms))

    async def _set_and_place(self, rule_set_id: uuid.UUID) -> tuple[PricingRuleSet, PricedProperty]:
        rule_set = await self._sets.get(rule_set_id)
        if rule_set is None:
            raise NotFoundError
        place = await self._catalog.priced_property_by_id(rule_set.property_id)
        assert place is not None  # noqa: S101 - a set's PG exists (foreign key)
        return rule_set, place

    async def _weeks(
        self,
        pricing: PgPricing,
        category: PricedCategory,
        move_ins: list[date],
        stay_months: int,
        today: date,
    ) -> tuple[CalendarWeek, ...] | None:
        """The room's rent for each move-in, as a quote would say; None when its bounds leave
        no rent."""
        weeks = []
        for move_in in move_ins:
            context = await self._inputs.context(pricing, category, move_in, stay_months, today)
            try:
                result = quote(context)
            except ImpossibleBoundsError:
                return None
            weeks.append(
                CalendarWeek(
                    move_in,
                    result.monthly_rent_paise,
                    tuple(clamp.kind for clamp in result.clamps),
                )
            )
        return tuple(weeks)

    async def get(self, quote_id: uuid.UUID) -> QuoteView:
        async with self._db.begin():
            row = await self._quote(quote_id)
            return await self._view(row)

    async def usable(self, quote_id: uuid.UUID) -> PriceQuote:
        """A quote a booking may take (Phase 5): 409 QUOTE_EXPIRED once its 30 minutes are up.
        In the caller's transaction."""
        row = await self._quote(quote_id)
        if row.expires_at <= self._clock.now():
            raise QuoteExpiredError
        return row

    async def _quote(self, quote_id: uuid.UUID) -> PriceQuote:
        row = await self._quotes.get(quote_id)
        if row is None:
            raise NotFoundError
        return row

    async def _view(self, row: PriceQuote) -> QuoteView:
        place = await self._catalog.priced_property_by_id(row.property_id)
        assert place is not None  # noqa: S101 - a quote's PG exists (foreign key)
        category = next(item for item in place.categories if item.id == row.room_category_id)
        return QuoteView(row, place, category, expired=row.expires_at <= self._clock.now())
