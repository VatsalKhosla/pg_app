"""An owner's business at a glance (ADR 0071): the tenants we placed, month by month. Pure.

Everything here is our own record of stays booked through us. Rent after the first month goes
straight to the owner, so "rent" is what those stays were booked at, never what was collected.
A stay counts in a month when the tenant lived there on any day of it.
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# The overview looks back two years at most, and at least a quarter.
MIN_MONTHS: Final = 3
MAX_MONTHS: Final = 24
DECEMBER: Final = 12


@dataclass(frozen=True, slots=True)
class Stay:
    """A tenant we placed: from the move-in day to the day they left (or will), and the monthly
    rent the stay was booked at (price-locked, CLAUDE.md rule 5)."""

    move_in: date
    # The first day they're no longer there: the move-out day, or the planned one.
    ends: date
    monthly_rent_paise: int
    stay_months: int

    def on(self, day: date) -> bool:
        return self.move_in <= day < self.ends

    def overlaps(self, start: date, end: date) -> bool:
        """Whether they lived there on any day of ``[start, end)``."""
        return self.move_in < end and self.ends > start


def next_month(first: date) -> date:
    if first.month == DECEMBER:
        return date(first.year + 1, 1, 1)
    return date(first.year, first.month + 1, 1)


def month_starts(today: date, months: int) -> list[date]:
    """The first days of the last ``months`` months, oldest first, this month's last."""
    year, month = today.year, today.month
    firsts: list[date] = []
    for _ in range(months):
        firsts.append(date(year, month, 1))
        year, month = (year - 1, DECEMBER) if month == 1 else (year, month - 1)
    return firsts[::-1]


def rent_by_month(stays: Iterable[Stay], months: Sequence[date]) -> list[int]:
    """Each month's booked monthly rent of the tenants who lived there on any day of it."""
    stays = list(stays)
    return [
        sum(stay.monthly_rent_paise for stay in stays if stay.overlaps(first, next_month(first)))
        for first in months
    ]


def move_ins_by_month(stays: Iterable[Stay], months: Sequence[date]) -> list[int]:
    """How many of the tenants moved in during each month."""
    stays = list(stays)
    return [
        sum(1 for stay in stays if first <= stay.move_in < next_month(first)) for first in months
    ]


def living_on(stays: Iterable[Stay], day: date) -> list[Stay]:
    """The tenants living there on ``day``."""
    return [stay for stay in stays if stay.on(day)]


def booked_rent(stays: Iterable[Stay]) -> int:
    """Every stay's rent for all the months it was booked for."""
    return sum(stay.monthly_rent_paise * stay.stay_months for stay in stays)
