"""Quotes (ARCHITECTURE §8.4; step 4.4, ADR 0039); each method is one transaction.

A quote prices one room category of a PG the public may see, for a move-in and a stay: the
policies in force, the PG's active rule set, the band for its locality and occupancy, and how full
the category is that day go into the engine, and the answer is stored with all of them, its
explanation, and the category's deposit and charges as they stood. It stands for 30 minutes; a
booking (Phase 5) takes only one that hasn't expired, and copies its money.
"""

from dataclasses import dataclass
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
from app.modules.pricing.domain.engine import ImpossibleBoundsError, PricingContext, quote
from app.modules.pricing.domain.quotes import (
    QUOTE_TTL,
    explanation,
    inputs_digest,
    quote_problems,
)
from app.modules.pricing.domain.rule_sets import RuleSetStatus
from app.modules.pricing.errors import PricingConfigError, QuoteExpiredError, QuoteInvalidError
from app.modules.pricing.models import (
    BookingPolicyVersion,
    FeePolicyVersion,
    PriceQuote,
    PricingCapsVersion,
)
from app.modules.pricing.repository import (
    PolicyRepository,
    QuoteRepository,
    RentBandRepository,
    RuleSetRepository,
)
from app.modules.pricing.service.policies import band_of, booking_policy, fee_policy, pricing_caps
from app.modules.pricing.service.rule_sets import domain_rule

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.flags import FlagReader
    from app.modules.pricing.occupancy import BedsTaken

logger = structlog.stdlib.get_logger(__name__)


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
                "type": "one_time",
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
        self._beds = beds
        self._catalog = CatalogLookup(db)
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
            fee_row = await self._policies.in_force(FeePolicyVersion, at=now)
            booking_row = await self._policies.in_force(BookingPolicyVersion, at=now)
            caps_row = await self._policies.in_force(PricingCapsVersion, at=now)
            if fee_row is None or booking_row is None or caps_row is None:
                raise PricingConfigError
            booking = booking_policy(booking_row)
            if problems := quote_problems(
                move_in=move_in, stay_months=stay_months, today=today, booking=booking
            ):
                raise QuoteInvalidError(problems)
            rule_set = await self._sets.in_status(place.id, RuleSetStatus.ACTIVE)
            rules = () if rule_set is None else await self._sets.rules_of(rule_set.id)
            band_row = await self._bands.in_force(place.locality_id, category.occupancy, at=now)
            context = PricingContext(
                room_category_id=category.id,
                base_rent_paise=category.base_rent,
                owner_min_paise=category.owner_min,
                owner_max_paise=category.owner_max,
                move_in=move_in,
                stay_months=stay_months,
                today=today,
                occupancy_bps=await self._beds.occupancy_bps(category.id, move_in),
                rules=tuple(domain_rule(row) for row in rules),
                band=None if band_row is None else band_of(band_row),
                fee_policy=fee_policy(fee_row),
                booking_policy=booking,
                caps=pricing_caps(caps_row),
            )
            try:
                result = quote(context)
            except ImpossibleBoundsError as error:
                # Ops' to fix (the owner's bounds against the band); nothing is quoted meanwhile.
                logger.error("no rent the bounds allow", property=str(place.public_id))
                msg = "This room can't be priced right now; our team has been told."
                raise PricingConfigError(msg) from error
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
