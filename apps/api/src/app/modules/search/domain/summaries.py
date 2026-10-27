"""Price summaries (ARCHITECTURE §6, §18; step 3.1, ADR 0027): each room category's rent range for
each month a student can move in, worked out ahead so search and the map never price a listing
per request.

This is the base-rent version: every month's range is the category's base rent, which is what a
quote charges until the pricing engine arrives (Phase 4) and gives each month its own range.
Every active bed counts as free until bookings exist (Phase 5).
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.money import Paise

# The month a student is in and the next six: six months ahead are there even on the morning a
# month turns, before the nightly refresh.
SUMMARY_MONTHS: Final = 7


@dataclass(frozen=True, slots=True)
class CategoryRent:
    category_id: int
    base_rent: Paise
    active_beds: int
    # What search filters categories by (step 3.2): its sharing, AC and attached bath.
    occupancy: str
    ac: bool
    attached_bath: bool


@dataclass(frozen=True, slots=True)
class MonthSummary:
    category_id: int
    # The month's first day.
    month: date
    min_rent: Paise
    max_rent: Paise
    available_beds: int
    occupancy: str
    ac: bool
    attached_bath: bool


def months_from(today: date, count: int = SUMMARY_MONTHS) -> list[date]:
    """The first days of ``count`` months, starting with ``today``'s."""
    months = []
    for offset in range(count):
        years, month_index = divmod(today.month - 1 + offset, 12)
        months.append(date(today.year + years, month_index + 1, 1))
    return months


def summarise(categories: Sequence[CategoryRent], months: Sequence[date]) -> list[MonthSummary]:
    """One summary per category and month: the base rent as both ends of the range."""
    return [
        MonthSummary(
            category_id=category.category_id,
            month=month,
            min_rent=category.base_rent,
            max_rent=category.base_rent,
            available_beds=category.active_beds,
            occupancy=category.occupancy,
            ac=category.ac,
            attached_bath=category.attached_bath,
        )
        for category in categories
        for month in months
    ]
