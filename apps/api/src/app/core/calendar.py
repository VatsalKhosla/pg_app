"""Dates in India. Pure: moments come in as arguments, so domain code may use this freely.

Timestamps are stored and compared in UTC; calendar dates that people see (move-in, check-in,
cancellation cutoffs) are dates in Asia/Kolkata (CLAUDE.md).
"""

from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from datetime import date, datetime

INDIA: Final = ZoneInfo("Asia/Kolkata")


def india_date(moment: datetime) -> date:
    """The calendar date in India at ``moment`` (which must be timezone-aware)."""
    if moment.tzinfo is None:
        msg = "moment must be timezone-aware"
        raise ValueError(msg)
    return moment.astimezone(INDIA).date()
