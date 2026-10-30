"""Beds over time (ARCHITECTURE §6 and §7.3; step 5.1, ADR 0044). Pure.

An allocation holds one bed for a period of days: a booking (Phase 5's holds onwards), an
offline tenant the owner placed without us, or maintenance. Periods are half-open,
``[start, end)``: a stay that moves out on the 1st frees the bed for a move-in that day. An
open end means "until further notice". The database refuses two active allocations of one
bed whose periods overlap; this module says what a bed's free and how full a room type is.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.money import BPS_PER_WHOLE

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

NOTE_MAX_LENGTH: Final = 300
# A block's furthest start, and the longest a closed one may run: past these it's a typo.
MAX_DAYS_AHEAD: Final = 366 * 2
MAX_DAYS: Final = 366 * 5


class AllocationKind(StrEnum):
    BOOKING = "booking"
    OFFLINE_TENANT = "offline_tenant"
    MAINTENANCE = "maintenance"


# What ops may place by hand; bookings come from the booking flow.
BLOCK_KINDS: Final = frozenset({AllocationKind.OFFLINE_TENANT, AllocationKind.MAINTENANCE})


@dataclass(frozen=True, slots=True)
class Period:
    """The days ``[start, end)``; ``end`` None for until further notice."""

    start: date
    end: date | None = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end <= self.start:
            msg = "a period ends after it starts"
            raise ValueError(msg)

    def overlaps(self, other: Period) -> bool:
        return (self.end is None or other.start < self.end) and (
            other.end is None or self.start < other.end
        )

    def holds(self, day: date) -> bool:
        return self.start <= day and (self.end is None or day < self.end)


def stay_period(move_in: date, stay_months: int) -> Period:
    """A stay's days: from the move-in, ``stay_months`` calendar months on, clamped to the
    month's last day (31 Jan + 1 month moves out on 28 or 29 Feb)."""
    years, month_index = divmod(move_in.month - 1 + stay_months, 12)
    year, month = move_in.year + years, month_index + 1
    following = date(year + month // 12, month % 12 + 1, 1)
    last_day = (following - timedelta(days=1)).day
    return Period(move_in, date(year, month, min(move_in.day, last_day)))


def block_problems(kind: AllocationKind, period: Period, *, today: date, note: str) -> list[str]:
    """What stops ops placing this block; empty when nothing does."""
    problems = []
    if kind not in BLOCK_KINDS:
        problems.append("only an offline tenant or maintenance can be placed by hand")
    if period.start > today + timedelta(days=MAX_DAYS_AHEAD):
        problems.append("a block starts at most two years ahead")
    if period.end is not None and (period.end - period.start).days > MAX_DAYS:
        problems.append("a block with an end runs at most five years")
    if len(note) > NOTE_MAX_LENGTH:
        problems.append(f"a note has at most {NOTE_MAX_LENGTH} characters")
    return problems


def free_beds(
    beds: Collection[int], allocations: Iterable[tuple[int, Period]], period: Period
) -> set[int]:
    """The beds no allocation holds on any day of ``period``: the plain definition the
    database's availability queries are tested against."""
    taken = {bed for bed, held in allocations if held.overlaps(period)}
    return {bed for bed in beds if bed not in taken}


@dataclass(frozen=True, slots=True)
class RoomBeds:
    """A room's beds that can be sold, by internal id."""

    room_id: int
    bed_ids: tuple[int, ...]


def choose_bed(
    rooms: Iterable[RoomBeds], allocations: Iterable[tuple[int, Period]], period: Period
) -> int | None:
    """The bed a new booking takes for ``period`` (§7.3): a free one in a room partly held then,
    so whole rooms stay free for groups. Rooms with the fewest free beds come first, and the
    lowest bed id settles a tie. None when every bed is held on some day of the period."""
    taken = {bed for bed, held in allocations if held.overlaps(period)}
    best: tuple[bool, int, int] | None = None
    for room in rooms:
        free = [bed for bed in room.bed_ids if bed not in taken]
        if not free:
            continue
        # A room nobody holds sorts after every partly held one.
        rank = (len(free) == len(room.bed_ids), len(free), min(free))
        if best is None or rank < best:
            best = rank
    return None if best is None else best[2]


def occupancy_bps(active_beds: int, taken: int) -> int:
    """How full a room type is, out of 10,000: beds taken over its active beds (none: 0)."""
    if active_beds <= 0:
        return 0
    return min(taken, active_beds) * BPS_PER_WHOLE // active_beds
