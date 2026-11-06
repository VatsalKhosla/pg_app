"""What an owner's insights say (step 7.6, ADR 0063). Pure.

Numbers people can check: counts from our own records, and ratios worked out in whole basis
points, with nothing shown where there's nothing to divide by.
"""

from typing import Final

MAX_DAYS: Final = 90
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
