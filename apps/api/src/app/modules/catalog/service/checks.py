"""Checks the catalog's use cases share: text lengths, house rules, places, licence numbers."""

from typing import TYPE_CHECKING, Final

from app.core.geometry import NCR_BOUNDS
from app.modules.catalog.domain.listing import HOUSE_RULE_MAX_LENGTH, HOUSE_RULES_MAX
from app.modules.catalog.errors import ListingInvalidError

if TYPE_CHECKING:
    from collections.abc import Collection

    from app.core.geometry import Point

DESCRIPTION_MAX_LENGTH: Final = 5_000
ADDRESS_MAX_LENGTH: Final = 300
LICENCE_NUMBER_MAX_LENGTH: Final = 60


def text_problems(name: str, value: str, *, required: bool, max_length: int) -> list[str]:
    stripped = value.strip()
    if required and not stripped:
        return [f"{name} is required"]
    if len(stripped) > max_length:
        return [f"{name} is longer than {max_length} characters"]
    return []


def house_rule_problems(rules: Collection[str]) -> list[str]:
    if len(rules) > HOUSE_RULES_MAX:
        return [f"at most {HOUSE_RULES_MAX} house rules"]
    if any(not rule.strip() or len(rule.strip()) > HOUSE_RULE_MAX_LENGTH for rule in rules):
        return [f"each house rule needs 1 to {HOUSE_RULE_MAX_LENGTH} characters"]
    return []


def location_problems(point: Point) -> list[str]:
    return [] if NCR_BOUNDS.contains(point) else ["the location is outside Delhi NCR"]


def licence_problems(number: str | None) -> list[str]:
    if number is not None and not 0 < len(number.strip()) <= LICENCE_NUMBER_MAX_LENGTH:
        return [f"the licence number needs 1 to {LICENCE_NUMBER_MAX_LENGTH} characters"]
    return []


def check(problems: list[str]) -> None:
    if problems:
        raise ListingInvalidError(problems)
