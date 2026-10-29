"""The pricing engine (ARCHITECTURE §8; step 4.2, ADR 0037): one pure function, ``quote``, from
everything a price depends on to the monthly rent and what each side pays. No I/O and no clock:
the caller passes the day it is and the occupancy, so the same inputs always give the same quote.

The steps, in order (§8.3):

1. Each enabled rule for the room category that matches makes an adjustment. An override that
   matches sets the rent outright, and the other rules then don't apply.
2. Premiums and discounts are added up apart, and each is capped.
3. The rent is clamped to the owner's bounds and the locality's band, rounded to the step, and
   kept inside the bounds. It's never zero.
4. The fee is the policy's rate of the listed (base) rent, never of the dynamic price (rule 2).
   GST is added to it, or taken out of it. The token is the policy's, never more than the rent.

All upside goes to the owner (rule 4): a rule moves the rent, never the fee. Money is integer
paise, rounded half-up only where §8.3 says (rule 12).
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from app.core.money import BPS_PER_WHOLE, Paise, apply_bps, divide_round_half_up, round_to_step
from app.modules.pricing.domain.policies import (
    BookingPolicy,
    FeePolicy,
    GstMode,
    PricingCaps,
    RentBand,
)

# Changed whenever the algorithm does: every quote records the version that made it.
ENGINE_VERSION: Final = "1"
LABEL_MAX_LENGTH: Final = 40
_LEAP_YEAR: Final = 2000


class RuleKind(StrEnum):
    SEASON = "season"
    OCCUPANCY = "occupancy"
    EARLY_BIRD = "early_bird"
    LAST_MINUTE = "last_minute"
    LENGTH_OF_STAY = "length_of_stay"
    OVERRIDE = "override"


@dataclass(frozen=True, slots=True, order=True)
class MonthDay:
    """A day of the year, as a season's start or end: "07-15" is 15 July, any year."""

    month: int
    day: int

    def __post_init__(self) -> None:
        # Checked against a leap year, so 29 February is a day a season may start or end.
        date(_LEAP_YEAR, self.month, self.day)

    @classmethod
    def parse(cls, text: str) -> MonthDay:
        month, _, day = text.partition("-")
        if len(text) != len("MM-DD") or not (month.isdigit() and day.isdigit()):
            msg = f"not a month and day such as 07-15: {text!r}"
            raise ValueError(msg)
        return cls(int(month), int(day))

    @classmethod
    def of(cls, day: date) -> MonthDay:
        return cls(day.month, day.day)

    def __str__(self) -> str:
        return f"{self.month:02d}-{self.day:02d}"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class SeasonRule:
    """``bps`` up or down for move-ins from ``start`` to ``end``, both days included. A season
    may wrap the year (15 December to 15 January)."""

    start: MonthDay
    end: MonthDay
    bps: int

    def __post_init__(self) -> None:
        _require(self.bps != 0, "a season moves the rent up or down")


@dataclass(frozen=True, slots=True)
class OccupancyTier:
    min_occupancy_bps: int
    bps: int


@dataclass(frozen=True, slots=True)
class OccupancyRule:
    """A premium once the category's occupancy on move-in reaches a tier: the highest tier
    reached counts. Occupancy counts beds with a secured token or later, and offline tenants;
    beds merely held don't count, so holds can't push prices up (§8.2)."""

    tiers: tuple[OccupancyTier, ...]

    def __post_init__(self) -> None:
        _require(len(self.tiers) > 0, "occupancy needs a tier")
        thresholds = [tier.min_occupancy_bps for tier in self.tiers]
        _require(thresholds == sorted(set(thresholds)), "tiers go up, each from its own level")
        _require(
            all(0 < tier.min_occupancy_bps <= BPS_PER_WHOLE for tier in self.tiers),
            "a tier starts above 0% and at most at 100% occupancy",
        )
        _require(all(tier.bps > 0 for tier in self.tiers), "occupancy only adds a premium")


@dataclass(frozen=True, slots=True)
class EarlyBirdRule:
    """A discount for booking at least ``min_days_before`` the move-in."""

    min_days_before: int
    bps: int

    def __post_init__(self) -> None:
        _require(self.min_days_before > 0, "early-bird starts a day or more ahead")
        _require(self.bps < 0, "early-bird only takes a discount")


@dataclass(frozen=True, slots=True)
class LastMinuteRule:
    """A discount for booking at most ``max_days_before`` the move-in while the category's
    occupancy is at most ``max_occupancy_bps``."""

    max_days_before: int
    max_occupancy_bps: int
    bps: int

    def __post_init__(self) -> None:
        _require(self.max_days_before >= 0, "last-minute counts days from the move-in")
        _require(0 <= self.max_occupancy_bps < BPS_PER_WHOLE, "last-minute is for beds still empty")
        _require(self.bps < 0, "last-minute only takes a discount")


@dataclass(frozen=True, slots=True)
class StayTier:
    min_months: int
    bps: int


@dataclass(frozen=True, slots=True)
class LengthOfStayRule:
    """A discount for staying at least a tier's months: the highest tier reached counts."""

    tiers: tuple[StayTier, ...]

    def __post_init__(self) -> None:
        _require(len(self.tiers) > 0, "length of stay needs a tier")
        months = [tier.min_months for tier in self.tiers]
        _require(months == sorted(set(months)), "tiers go up, each from its own months")
        _require(all(tier.min_months > 1 for tier in self.tiers), "a tier starts above a month")
        _require(all(tier.bps < 0 for tier in self.tiers), "length of stay only takes a discount")


@dataclass(frozen=True, slots=True)
class OverrideRule:
    """A fixed monthly rent for move-ins from ``start`` to ``end``, both days included: the
    other rules then don't apply, but the bounds and rounding still do."""

    start: date
    end: date
    rent_paise: Paise

    def __post_init__(self) -> None:
        _require(self.start <= self.end, "an override ends on or after it starts")
        _require(self.rent_paise > 0, "an override sets a rent above zero")


type RuleParams = (
    SeasonRule | OccupancyRule | EarlyBirdRule | LastMinuteRule | LengthOfStayRule | OverrideRule
)

_KINDS: Final[dict[type[RuleParams], RuleKind]] = {
    SeasonRule: RuleKind.SEASON,
    OccupancyRule: RuleKind.OCCUPANCY,
    EarlyBirdRule: RuleKind.EARLY_BIRD,
    LastMinuteRule: RuleKind.LAST_MINUTE,
    LengthOfStayRule: RuleKind.LENGTH_OF_STAY,
    OverrideRule: RuleKind.OVERRIDE,
}


@dataclass(frozen=True, slots=True)
class PricingRule:
    """One rule of a PG's rule set, with the label students see ("Peak season")."""

    label: str
    params: RuleParams
    # The room categories it's for; None for all of the PG's.
    room_category_ids: frozenset[int] | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        _require(
            0 < len(self.label.strip()) <= LABEL_MAX_LENGTH,
            f"a rule's label has 1 to {LABEL_MAX_LENGTH} characters",
        )

    @property
    def kind(self) -> RuleKind:
        return _KINDS[type(self.params)]


@dataclass(frozen=True, slots=True)
class PricingContext:
    """Everything one quote depends on."""

    room_category_id: int
    # The category's listed monthly rent: what the fee is worked out on (rule 2).
    base_rent_paise: Paise
    owner_min_paise: Paise | None
    owner_max_paise: Paise | None
    move_in: date
    stay_months: int
    # The day the quote is made, in India.
    today: date
    # The category's beds taken on the move-in, out of 10,000.
    occupancy_bps: int
    # The PG's active rule set.
    rules: tuple[PricingRule, ...]
    band: RentBand | None
    fee_policy: FeePolicy
    booking_policy: BookingPolicy
    caps: PricingCaps

    def __post_init__(self) -> None:
        _require(self.base_rent_paise > 0, "the listed rent is above zero")
        _require(self.stay_months >= 1, "a stay is a month or more")
        _require(self.move_in >= self.today, "a move-in can't be in the past")
        _require(0 <= self.occupancy_bps <= BPS_PER_WHOLE, "occupancy is from 0 to 100%")


class ClampKind(StrEnum):
    PREMIUM_CAP = "premium_cap"
    DISCOUNT_CAP = "discount_cap"
    OWNER_MIN = "owner_min"
    OWNER_MAX = "owner_max"
    BAND_MIN = "band_min"
    BAND_MAX = "band_max"


@dataclass(frozen=True, slots=True)
class Adjustment:
    """A rule that moved the rent: by ``bps``, or for an override, to ``rent_paise``."""

    kind: RuleKind
    label: str
    bps: int | None
    rent_paise: Paise | None


@dataclass(frozen=True, slots=True)
class Clamp:
    """A limit that held the price back: what was asked for, and what was allowed (basis points
    for a cap, paise for a bound)."""

    kind: ClampKind
    asked: int
    allowed: int


@dataclass(frozen=True, slots=True)
class Quote:
    base_rent_paise: Paise
    # The rent for every month of the stay, fixed by the quote (rule 5).
    monthly_rent_paise: Paise
    adjustments: tuple[Adjustment, ...]
    clamps: tuple[Clamp, ...]
    premium_bps: int
    discount_bps: int
    # The owner's placement fee, its GST, and what the owner pays in all.
    fee_paise: Paise
    gst_paise: Paise
    owner_fee_total_paise: Paise
    # What the student pays to reserve, and the rest of the first month at move-in.
    token_paise: Paise
    due_at_move_in_paise: Paise
    engine_version: str


class ImpossibleBoundsError(ValueError):
    """The owner's bounds and the band leave no rent: ops must look, and nothing is quoted."""

    def __init__(self, low: int, high: int) -> None:
        super().__init__(f"the lowest rent allowed ({low}) is above the highest ({high})")
        self.low = low
        self.high = high


def _months_matching(tiers: tuple[StayTier, ...], months: int) -> int | None:
    reached = [tier.bps for tier in tiers if tier.min_months <= months]
    return reached[-1] if reached else None


def _occupancy_matching(tiers: tuple[OccupancyTier, ...], occupancy_bps: int) -> int | None:
    reached = [tier.bps for tier in tiers if tier.min_occupancy_bps <= occupancy_bps]
    return reached[-1] if reached else None


def _in_season(season: SeasonRule, move_in: date) -> bool:
    day = MonthDay.of(move_in)
    if season.start <= season.end:
        return season.start <= day <= season.end
    return day >= season.start or day <= season.end


def rule_bps(params: RuleParams, context: PricingContext) -> int | None:
    """What a rule moves the rent by for this context, or None if it doesn't match. An
    override's isn't in basis points: see ``quote``."""
    days_before = (context.move_in - context.today).days
    match params:
        case SeasonRule():
            return params.bps if _in_season(params, context.move_in) else None
        case OccupancyRule():
            return _occupancy_matching(params.tiers, context.occupancy_bps)
        case EarlyBirdRule():
            return params.bps if days_before >= params.min_days_before else None
        case LastMinuteRule():
            matches = (
                days_before <= params.max_days_before
                and context.occupancy_bps <= params.max_occupancy_bps
            )
            return params.bps if matches else None
        case LengthOfStayRule():
            return _months_matching(params.tiers, context.stay_months)
        case OverrideRule():
            return None


def _applies(rule: PricingRule, room_category_id: int) -> bool:
    return rule.enabled and (
        rule.room_category_ids is None or room_category_id in rule.room_category_ids
    )


def _override(rules: list[PricingRule], move_in: date) -> PricingRule | None:
    """The first override for the move-in, in the rule set's order (a valid set has at most one;
    step 4.3 checks)."""
    for rule in rules:
        params = rule.params
        if isinstance(params, OverrideRule) and params.start <= move_in <= params.end:
            return rule
    return None


def _floor_to_step(amount: int, step: int) -> int:
    return amount // step * step


def _ceil_to_step(amount: int, step: int) -> int:
    return -(-amount // step) * step


def bounds(context: PricingContext) -> tuple[int, int | None]:
    """The lowest and highest rent allowed (None for no highest): the owner's and the band's,
    the narrower of each. A rent is never below one paisa."""
    band = context.band
    lows = [1, context.owner_min_paise or 0, band.min_rent_paise if band is not None else 0]
    highs = [
        high
        for high in (context.owner_max_paise, band.max_rent_paise if band is not None else None)
        if high is not None
    ]
    return max(lows), (min(highs) if highs else None)


def _bound_clamps(
    context: PricingContext, candidate: int, low: int, high: int | None
) -> list[Clamp]:
    """Which bound held the candidate back, if one did: the band's when it's the tighter."""
    band = context.band
    if candidate < low:
        by_band = band is not None and band.min_rent_paise == low
        return [Clamp(ClampKind.BAND_MIN if by_band else ClampKind.OWNER_MIN, candidate, low)]
    if high is not None and candidate > high:
        by_band = band is not None and band.max_rent_paise == high
        return [Clamp(ClampKind.BAND_MAX if by_band else ClampKind.OWNER_MAX, candidate, high)]
    return []


def _bounded(candidate: int, low: int, high: int | None, step: int) -> int:
    """``candidate`` inside [low, high], rounded to the step, then kept inside: a multiple of
    the step unless no multiple fits between the bounds."""
    clamped = max(low, candidate) if high is None else min(max(low, candidate), high)
    price = round_to_step(clamped, step)
    if high is not None and price > high:
        below = _floor_to_step(high, step)
        price = below if below >= low else high
    if price < low:
        above = _ceil_to_step(low, step)
        price = above if high is None or above <= high else low
    return price


def owner_fee(base_rent_paise: int, policy: FeePolicy) -> tuple[Paise, Paise, Paise]:
    """The fee, its GST and the owner's total, from the listed rent alone (rule 2)."""
    fee = apply_bps(base_rent_paise, policy.rate_bps)
    if policy.gst_mode is GstMode.EXCLUSIVE:
        gst = apply_bps(fee, policy.gst_rate_bps)
        return Paise(fee), Paise(gst), Paise(fee + gst)
    net = divide_round_half_up(fee * BPS_PER_WHOLE, BPS_PER_WHOLE + policy.gst_rate_bps)
    return Paise(fee), Paise(fee - net), Paise(fee)


def quote(context: PricingContext) -> Quote:
    """The quote for ``context`` (§8.3). Raises ImpossibleBoundsError when the bounds leave no
    rent, rather than quote one outside them."""
    base = context.base_rent_paise
    caps = context.caps
    applying = [rule for rule in context.rules if _applies(rule, context.room_category_id)]
    clamps: list[Clamp] = []
    adjustments: tuple[Adjustment, ...]
    override = _override(applying, context.move_in)
    if override is not None:
        params = override.params
        assert isinstance(params, OverrideRule)  # noqa: S101 - _override found one
        adjustments = (Adjustment(RuleKind.OVERRIDE, override.label, None, params.rent_paise),)
        candidate = int(params.rent_paise)
        premium = discount = 0
    else:
        matched = [
            (rule, bps) for rule in applying if (bps := rule_bps(rule.params, context)) is not None
        ]
        adjustments = tuple(Adjustment(rule.kind, rule.label, bps, None) for rule, bps in matched)
        asked_premium = sum(bps for _, bps in matched if bps > 0)
        asked_discount = sum(-bps for _, bps in matched if bps < 0)
        premium = min(asked_premium, caps.max_premium_bps)
        discount = min(asked_discount, caps.max_discount_bps)
        if premium < asked_premium:
            clamps.append(Clamp(ClampKind.PREMIUM_CAP, asked_premium, premium))
        if discount < asked_discount:
            clamps.append(Clamp(ClampKind.DISCOUNT_CAP, asked_discount, discount))
        candidate = divide_round_half_up(base * (BPS_PER_WHOLE + premium - discount), BPS_PER_WHOLE)
    low, high = bounds(context)
    if high is not None and low > high:
        raise ImpossibleBoundsError(low, high)
    clamps += _bound_clamps(context, candidate, low, high)
    price = _bounded(candidate, low, high, caps.rounding_step_paise)
    fee, gst, total = owner_fee(base, context.fee_policy)
    token = min(context.booking_policy.token_paise, price)
    return Quote(
        base_rent_paise=base,
        monthly_rent_paise=Paise(price),
        adjustments=adjustments,
        clamps=tuple(clamps),
        premium_bps=premium,
        discount_bps=discount,
        fee_paise=fee,
        gst_paise=gst,
        owner_fee_total_paise=total,
        token_paise=Paise(token),
        due_at_move_in_paise=Paise(price - token),
        engine_version=ENGINE_VERSION,
    )
