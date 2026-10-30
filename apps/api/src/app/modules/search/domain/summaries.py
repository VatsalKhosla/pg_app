"""Price summaries (ARCHITECTURE §6, §18; steps 3.1 and 4.7, ADRs 0027 and 0042): each room
category's rent range for each month a student can move in, worked out ahead so search and the
map never price a listing per request.

A month's range is the least and the most the pricing engine quotes for a move-in on any day of
it still to come, for the common stay, so the map and search agree with the PG page. Its free beds
are those nothing holds for that stay from the month's first move-in (ADR 0044).
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

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


def summarise(
    categories: Sequence[CategoryRent],
    months: Sequence[date],
    rents: Mapping[tuple[int, date], tuple[Paise, Paise]],
    free_beds: Mapping[tuple[int, date], int],
) -> list[MonthSummary]:
    """One summary per category and month the engine priced: its range of rents for the month,
    lowest and highest, from ``rents`` by category and month, and its free beds from
    ``free_beds``. A category it couldn't price (its limits leave no rent) has none, so search
    shows no price for it."""
    summaries = []
    for category in categories:
        for month in months:
            found = rents.get((category.category_id, month))
            if found is None:
                continue
            summaries.append(
                MonthSummary(
                    category_id=category.category_id,
                    month=month,
                    min_rent=found[0],
                    max_rent=found[1],
                    available_beds=free_beds.get((category.category_id, month), 0),
                    occupancy=category.occupancy,
                    ac=category.ac,
                    attached_bath=category.attached_bath,
                )
            )
    return summaries
