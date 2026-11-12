"""What an owner's insights say (step 7.6, ADR 0063). Pure.

Numbers people can check: counts from our own records, and ratios worked out in whole basis
points, with nothing shown where there's nothing to divide by.
"""

from datetime import date, timedelta
from typing import Final

MAX_DAYS: Final = 90
# The staff dashboard looks back half a year at most.
MAX_WEEKS: Final = 26
BPS_PER_WHOLE: Final = 10_000


def conversion_bps(bookings: int, visits: int) -> int | None:
    """Bookings for each visit asked for, in basis points, rounded down; None without visits.
    It can pass 100%: students also book without a visit."""
    if visits <= 0:
        return None
    return bookings * BPS_PER_WHOLE // visits


def taken_bps(taken: int, beds: int) -> int | None:
    """How full the PG is today, in basis points, rounded down; None without beds."""
    if beds <= 0:
        return None
    return min(taken, beds) * BPS_PER_WHOLE // beds


def week_starts(today: date, weeks: int) -> list[date]:
    """The Mondays of the last ``weeks`` weeks, oldest first, this week's last."""
    monday = today - timedelta(days=today.weekday())
    return [monday - timedelta(weeks=weeks - 1 - index) for index in range(weeks)]


def series(weeks: list[date], counts: dict[date, int]) -> list[int]:
    """One number a week, zero where nothing happened."""
    return [counts.get(week, 0) for week in weeks]
