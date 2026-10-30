"""What the engine needs for a PG's prices (ADRs 0039 to 0042): the policies and bands in force, a
rule set's rules, and each room's occupancy on a move-in. Built the same way for quotes, the PG
page's calendar, ops' previews and charts, and search's price summaries, so they all agree. In the
caller's transaction (it starts none).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.pricing.domain.engine import PricingContext
from app.modules.pricing.domain.rule_sets import RuleSetStatus
from app.modules.pricing.errors import PricingConfigError
from app.modules.pricing.models import BookingPolicyVersion, FeePolicyVersion, PricingCapsVersion
from app.modules.pricing.repository import PolicyRepository, RentBandRepository, RuleSetRepository
from app.modules.pricing.service.policies import band_of, booking_policy, fee_policy, pricing_caps
from app.modules.pricing.service.rule_sets import domain_rule

if TYPE_CHECKING:
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.catalog.domain.rooms import Occupancy
    from app.modules.catalog.service import PricedCategory, PricedProperty
    from app.modules.pricing.domain.engine import PricingRule
    from app.modules.pricing.domain.policies import BookingPolicy
    from app.modules.pricing.models import PricingRuleSet
    from app.modules.pricing.models import RentBand as RentBandRow
    from app.modules.pricing.occupancy import BedsTaken, RoomOccupancy


@dataclass(frozen=True, slots=True)
class PgPricing:
    """Everything a PG's prices depend on but the room, the move-in and the stay."""

    fee_row: FeePolicyVersion
    booking_row: BookingPolicyVersion
    caps_row: PricingCapsVersion
    booking: BookingPolicy
    rule_set: PricingRuleSet | None
    rules: tuple[PricingRule, ...]
    bands: dict[Occupancy, RentBandRow | None]


class PricingInputs:
    def __init__(self, db: AsyncSession, *, beds: BedsTaken) -> None:
        self._db = db
        self._beds = beds
        # Each category's occupancy, read once for this pass.
        self._occupancy: dict[int, RoomOccupancy] = {}
        self._policies = PolicyRepository(db)
        self._sets = RuleSetRepository(db)
        self._bands = RentBandRepository(db)

    async def active(self, place: PricedProperty, *, now: datetime) -> PgPricing:
        """What the PG's prices depend on now: the policies, its active rule set, its bands."""
        rule_set = await self._sets.in_status(place.id, RuleSetStatus.ACTIVE)
        return await self.of(place, now=now, rule_set=rule_set)

    async def of(
        self, place: PricedProperty, *, now: datetime, rule_set: PricingRuleSet | None
    ) -> PgPricing:
        """The policies and bands in force now, with ``rule_set``'s rules (none: no rules)."""
        fee_row = await self._policies.in_force(FeePolicyVersion, at=now)
        booking_row = await self._policies.in_force(BookingPolicyVersion, at=now)
        caps_row = await self._policies.in_force(PricingCapsVersion, at=now)
        if fee_row is None or booking_row is None or caps_row is None:
            raise PricingConfigError
        rules = () if rule_set is None else await self._sets.rules_of(rule_set.id)
        bands = {
            occupancy: await self._bands.in_force(place.locality_id, occupancy, at=now)
            for occupancy in {category.occupancy for category in place.categories}
        }
        return PgPricing(
            fee_row=fee_row,
            booking_row=booking_row,
            caps_row=caps_row,
            booking=booking_policy(booking_row),
            rule_set=rule_set,
            rules=tuple(domain_rule(row) for row in rules),
            bands=bands,
        )

    async def context(
        self,
        pricing: PgPricing,
        category: PricedCategory,
        move_in: date,
        stay_months: int,
        today: date,
    ) -> PricingContext:
        """The engine's input for one room, move-in and stay, quoted on ``today``."""
        band_row = pricing.bands.get(category.occupancy)
        return PricingContext(
            room_category_id=category.id,
            base_rent_paise=category.base_rent,
            owner_min_paise=category.owner_min,
            owner_max_paise=category.owner_max,
            move_in=move_in,
            stay_months=stay_months,
            today=today,
            occupancy_bps=(await self._occupancy_of(category.id)).bps_on(move_in),
            rules=pricing.rules,
            band=None if band_row is None else band_of(band_row),
            fee_policy=fee_policy(pricing.fee_row),
            booking_policy=pricing.booking,
            caps=pricing_caps(pricing.caps_row),
        )

    async def _occupancy_of(self, category_id: int) -> RoomOccupancy:
        if (found := self._occupancy.get(category_id)) is None:
            found = await self._beds.occupancy(self._db, category_id)
            self._occupancy[category_id] = found
        return found
