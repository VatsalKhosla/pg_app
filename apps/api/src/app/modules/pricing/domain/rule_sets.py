"""A PG's rule sets (ARCHITECTURE §6 and §8.6; step 4.3, ADR 0038). Pure.

A PG prices with one rule set at a time. Changes go into a draft; activating it makes it the set
in force and archives the one before, in one step. Active and archived sets never change again,
so a quote that names its set can always be explained. What a set may hold is checked when it's
activated, and each problem is said in words ops can act on.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.money import Paise, format_inr
from app.modules.pricing.domain.engine import (
    EarlyBirdRule,
    LastMinuteRule,
    LengthOfStayRule,
    MonthDay,
    OccupancyRule,
    OccupancyTier,
    OverrideRule,
    PricingRule,
    RuleKind,
    RuleParams,
    SeasonRule,
    StayTier,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from app.modules.pricing.domain.policies import RentBand

# A set holds this many rules at most: plenty for a PG, and an editor's page.
MAX_RULES: Final = 30
_YEAR: Final = 2000  # a leap year, so 29 February is a day like any other


class RuleSetStatus(StrEnum):
    # Being edited.
    DRAFT = "draft"
    # In force: what quotes use.
    ACTIVE = "active"
    # In force once; kept, unchanged, for the quotes and bookings it priced.
    ARCHIVED = "archived"


_NEXT: Final = {
    RuleSetStatus.DRAFT: frozenset({RuleSetStatus.ACTIVE}),
    RuleSetStatus.ACTIVE: frozenset({RuleSetStatus.ARCHIVED}),
}


def can_move(current: RuleSetStatus, target: RuleSetStatus) -> bool:
    return target in _NEXT.get(current, frozenset())


# The rules' parameters as the database keeps them (JSON).


type Json = str | int | list[dict[str, int]]


def params_to_json(params: RuleParams) -> dict[str, Json]:
    match params:
        case SeasonRule():
            return {"start": str(params.start), "end": str(params.end), "bps": params.bps}
        case OccupancyRule():
            return {
                "tiers": [
                    {"min_occupancy_bps": tier.min_occupancy_bps, "bps": tier.bps}
                    for tier in params.tiers
                ]
            }
        case EarlyBirdRule():
            return {"min_days_before": params.min_days_before, "bps": params.bps}
        case LastMinuteRule():
            return {
                "max_days_before": params.max_days_before,
                "max_occupancy_bps": params.max_occupancy_bps,
                "bps": params.bps,
            }
        case LengthOfStayRule():
            return {
                "tiers": [{"min_months": tier.min_months, "bps": tier.bps} for tier in params.tiers]
            }
        case OverrideRule():
            return {
                "start": params.start.isoformat(),
                "end": params.end.isoformat(),
                "rent_paise": params.rent_paise,
            }


def _int(data: Mapping[str, object], name: str) -> int:
    value = data.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{name} must be a whole number"
        raise ValueError(msg)
    return value


def _text(data: Mapping[str, object], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str):
        msg = f"{name} must be text"
        raise ValueError(msg)
    return value


def _tiers(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = data.get("tiers")
    if not isinstance(value, list) or not all(isinstance(tier, dict) for tier in value):
        msg = "tiers must be a list"
        raise ValueError(msg)
    return value


def params_from_json(kind: RuleKind, data: Mapping[str, object]) -> RuleParams:
    """The parameters stored for a rule of ``kind``; ValueError if they can't be one."""
    match kind:
        case RuleKind.SEASON:
            return SeasonRule(
                MonthDay.parse(_text(data, "start")),
                MonthDay.parse(_text(data, "end")),
                _int(data, "bps"),
            )
        case RuleKind.OCCUPANCY:
            return OccupancyRule(
                tuple(
                    OccupancyTier(_int(tier, "min_occupancy_bps"), _int(tier, "bps"))
                    for tier in _tiers(data)
                )
            )
        case RuleKind.EARLY_BIRD:
            return EarlyBirdRule(_int(data, "min_days_before"), _int(data, "bps"))
        case RuleKind.LAST_MINUTE:
            return LastMinuteRule(
                _int(data, "max_days_before"), _int(data, "max_occupancy_bps"), _int(data, "bps")
            )
        case RuleKind.LENGTH_OF_STAY:
            return LengthOfStayRule(
                tuple(
                    StayTier(_int(tier, "min_months"), _int(tier, "bps")) for tier in _tiers(data)
                )
            )
        case RuleKind.OVERRIDE:
            return OverrideRule(
                date.fromisoformat(_text(data, "start")),
                date.fromisoformat(_text(data, "end")),
                Paise(_int(data, "rent_paise")),
            )


# What a set may hold.


@dataclass(frozen=True, slots=True)
class CategoryBounds:
    """A room category as checking a set needs it: its name for ops, its rents, its band."""

    category_id: int
    name: str
    base_rent_paise: Paise
    owner_min_paise: Paise | None
    owner_max_paise: Paise | None
    band: RentBand | None


def _days(season: SeasonRule) -> set[int]:
    """A season's days of the year (1 to 366)."""
    start = date(_YEAR, season.start.month, season.start.day).timetuple().tm_yday
    end = date(_YEAR, season.end.month, season.end.day).timetuple().tm_yday
    if start <= end:
        return set(range(start, end + 1))
    return set(range(start, 367)) | set(range(1, end + 1))


def _day_name(day_of_year: int) -> str:
    return str(MonthDay.of(date(_YEAR, 1, 1) + timedelta(days=day_of_year - 1)))


def _for(rule: PricingRule, category: CategoryBounds) -> bool:
    return rule.enabled and (
        rule.room_category_ids is None or category.category_id in rule.room_category_ids
    )


def _pairs[T](items: Sequence[T]) -> Iterator[tuple[T, T]]:
    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            yield first, second


def _overlaps(rules: Sequence[PricingRule], categories: Sequence[CategoryBounds]) -> Iterator[str]:
    """Seasons whose days meet, or overrides whose dates meet, for a room category."""
    for category in categories:
        seasons = [
            rule for rule in rules if isinstance(rule.params, SeasonRule) and _for(rule, category)
        ]
        for first, second in _pairs(seasons):
            assert isinstance(first.params, SeasonRule)  # noqa: S101 - just filtered
            assert isinstance(second.params, SeasonRule)  # noqa: S101 - just filtered
            shared = sorted(_days(first.params) & _days(second.params))
            if shared:
                yield (
                    f"the seasons '{first.label}' and '{second.label}' both cover"
                    f" {_day_name(shared[0])} for {category.name}: seasons may not overlap"
                )
        overrides = [
            rule for rule in rules if isinstance(rule.params, OverrideRule) and _for(rule, category)
        ]
        for first, second in _pairs(overrides):
            assert isinstance(first.params, OverrideRule)  # noqa: S101 - just filtered
            assert isinstance(second.params, OverrideRule)  # noqa: S101 - just filtered
            if first.params.start <= second.params.end and second.params.start <= first.params.end:
                later = max(first.params.start, second.params.start)
                yield (
                    f"the overrides '{first.label}' and '{second.label}' both cover"
                    f" {later.isoformat()} for {category.name}: one rent a day"
                )


def _bound_problems(category: CategoryBounds) -> Iterator[str]:
    band = category.band
    lows = [low for low in (category.owner_min_paise, band.min_rent_paise if band else None) if low]
    highs = [
        high for high in (category.owner_max_paise, band.max_rent_paise if band else None) if high
    ]
    if lows and highs and max(lows) > min(highs):
        yield (
            f"{category.name} has no rent it may charge: the lowest allowed,"
            f" {format_inr(max(lows))}, is above the highest, {format_inr(min(highs))}"
        )


def _band_conflicts(rules: Sequence[PricingRule], category: CategoryBounds) -> Iterator[str]:
    """An override's rent the band wouldn't let it charge."""
    band = category.band
    if band is None:
        return
    for rule in rules:
        params = rule.params
        if not (isinstance(params, OverrideRule) and _for(rule, category)):
            continue
        if not band.min_rent_paise <= params.rent_paise <= band.max_rent_paise:
            yield (
                f"the override '{rule.label}' sets {format_inr(params.rent_paise)} for"
                f" {category.name}, outside its locality's band of"
                f" {format_inr(band.min_rent_paise)} to {format_inr(band.max_rent_paise)}"
            )


def rule_set_problems(
    rules: Sequence[PricingRule],
    categories: Sequence[CategoryBounds],
    *,
    known: Callable[[int], bool] | None = None,
) -> list[str]:
    """What stops ``rules`` going into force for the PG's ``categories``: overlapping seasons
    or overrides, band conflicts, bounds that leave no rent, and rules for room categories the
    PG doesn't have. Empty when the set may be activated."""
    is_known = known or (lambda category_id: any(c.category_id == category_id for c in categories))
    problems: list[str] = []
    if len(rules) > MAX_RULES:
        problems.append(f"a set holds {MAX_RULES} rules at most")
    for rule in rules:
        unknown = [cid for cid in rule.room_category_ids or () if not is_known(cid)]
        if unknown:
            problems.append(f"'{rule.label}' is for a room category this PG doesn't have")
    problems += _overlaps(rules, categories)
    for category in categories:
        problems += _bound_problems(category)
        problems += _band_conflicts(rules, category)
    return problems
