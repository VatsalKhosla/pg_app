"""Room categories, rooms and beds (ARCHITECTURE §6).

A room category is the unit students choose and the unit prices are set for: a double AC room
with an attached bath, say, at a base rent per bed per month. Its rooms hold beds, the units
bookings take, and a room holds no more beds than its occupancy says.

Rents are integer paise. The base (listed) rent is what a bed costs when no pricing rule applies,
and the placement fee is worked out on it (CLAUDE.md rules 2 and 12). An owner's minimum and
maximum, when given, bound what rules may do to it (rule 6), so the base rent must lie between
them.
"""

from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from app.core.money import Paise

LABEL_MAX_LENGTH: Final = 80
# Floors from basement levels to the tallest buildings PGs are in.
LOWEST_FLOOR: Final = -3
HIGHEST_FLOOR: Final = 60


class Occupancy(StrEnum):
    SINGLE = "single"
    DOUBLE = "double"
    TRIPLE = "triple"
    QUAD = "quad"


BEDS_PER_ROOM: Final = {
    Occupancy.SINGLE: 1,
    Occupancy.DOUBLE: 2,
    Occupancy.TRIPLE: 3,
    Occupancy.QUAD: 4,
}


class CategoryStatus(StrEnum):
    ACTIVE = "active"
    # Not offered: no new bookings, and not counted for publishing.
    INACTIVE = "inactive"


class BedStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


def rent_problems(
    *,
    base_rent: Paise,
    owner_min: Paise | None,
    owner_max: Paise | None,
    deposit: Paise,
) -> list[str]:
    """What is wrong with a category's money; empty when nothing is."""
    problems = []
    if base_rent <= 0:
        problems.append("the base rent must be more than zero")
    if owner_min is not None and owner_min <= 0:
        problems.append("the owner's minimum must be more than zero")
    if owner_min is not None and owner_min > base_rent:
        problems.append("the base rent can't be below the owner's minimum")
    if owner_max is not None and owner_max < base_rent:
        problems.append("the base rent can't be above the owner's maximum")
    if deposit < 0:
        problems.append("the deposit can't be negative")
    return problems


def room_has_space(occupancy: Occupancy, beds: int) -> bool:
    """Whether a room of this occupancy, already holding ``beds``, can take another."""
    return beds < BEDS_PER_ROOM[occupancy]
