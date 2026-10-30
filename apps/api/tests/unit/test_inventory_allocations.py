"""Beds over time (step 5.1, ADR 0044), without a database: periods, a stay's days, what ops
may block, availability by its plain definition, and occupancy."""

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.inventory.domain.allocations import (
    AllocationKind,
    Period,
    block_problems,
    free_beds,
    occupancy_bps,
    stay_period,
)

TODAY = date(2027, 7, 14)
JULY = Period(date(2027, 7, 1), date(2027, 8, 1))


def test_a_period_ends_after_it_starts() -> None:
    with pytest.raises(ValueError, match="ends after it starts"):
        Period(TODAY, TODAY)
    assert Period(TODAY).end is None


@pytest.mark.parametrize(
    ("other", "overlaps"),
    [
        # Moving out on the 1st frees the bed for a move-in that day.
        (Period(date(2027, 8, 1), date(2027, 9, 1)), False),
        (Period(date(2027, 6, 1), date(2027, 7, 1)), False),
        (Period(date(2027, 7, 31), date(2027, 8, 2)), True),
        (Period(date(2027, 6, 1)), True),
        (Period(date(2027, 8, 1)), False),
    ],
)
def test_periods_overlap_on_a_shared_day(other: Period, overlaps: bool) -> None:
    assert JULY.overlaps(other) is overlaps
    assert other.overlaps(JULY) is overlaps


def test_a_period_holds_its_days_but_not_its_end() -> None:
    assert JULY.holds(date(2027, 7, 1))
    assert JULY.holds(date(2027, 7, 31))
    assert not JULY.holds(date(2027, 8, 1))
    assert not JULY.holds(date(2027, 6, 30))
    assert Period(date(2027, 7, 1)).holds(date(2030, 1, 1))


def test_a_stay_runs_whole_months_clamped_to_a_months_end() -> None:
    assert stay_period(date(2027, 7, 14), 11) == Period(date(2027, 7, 14), date(2028, 6, 14))
    assert stay_period(date(2027, 1, 31), 1) == Period(date(2027, 1, 31), date(2027, 2, 28))
    assert stay_period(date(2028, 1, 31), 1) == Period(date(2028, 1, 31), date(2028, 2, 29))
    assert stay_period(date(2027, 12, 15), 2) == Period(date(2027, 12, 15), date(2028, 2, 15))


def test_ops_place_only_blocks_that_make_sense() -> None:
    fine = Period(TODAY, TODAY + timedelta(days=30))
    assert block_problems(AllocationKind.OFFLINE_TENANT, fine, today=TODAY, note="") == []
    assert block_problems(AllocationKind.MAINTENANCE, Period(TODAY), today=TODAY, note="") == []
    assert block_problems(
        AllocationKind.BOOKING,
        Period(TODAY + timedelta(days=800), TODAY + timedelta(days=2_700)),
        today=TODAY,
        note="x" * 301,
    ) == [
        "only an offline tenant or maintenance can be placed by hand",
        "a block starts at most two years ahead",
        "a block with an end runs at most five years",
        "a note has at most 300 characters",
    ]


def test_a_bed_is_free_when_nothing_holds_it_on_any_day() -> None:
    held = [(1, JULY), (2, Period(date(2027, 9, 1))), (3, Period(date(2027, 1, 1), TODAY))]

    assert free_beds({1, 2, 3, 4}, held, Period(date(2027, 7, 20), date(2027, 8, 20))) == {
        2,
        3,
        4,
    }
    # Bed 2's block starts on 1 September, the last day wanted.
    assert free_beds({1, 2, 3, 4}, held, Period(date(2027, 8, 1), date(2027, 9, 2))) == {1, 3, 4}


def test_occupancy_is_taken_over_active_beds_rounded_down() -> None:
    assert [occupancy_bps(3, taken) for taken in range(4)] == [0, 3_333, 6_666, 10_000]
    assert (occupancy_bps(0, 0), occupancy_bps(2, 5)) == (0, 10_000)


days = st.integers(min_value=0, max_value=400)


@st.composite
def periods(draw: st.DrawFn) -> Period:
    start = TODAY + timedelta(days=draw(days))
    length = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=200)))
    return Period(start, None if length is None else start + timedelta(days=length))


@given(
    st.lists(st.tuples(st.integers(min_value=1, max_value=6), periods()), max_size=12), periods()
)
def test_a_free_bed_has_no_day_in_common_with_any_allocation(
    held: list[tuple[int, Period]], wanted: Period
) -> None:
    free = free_beds(set(range(1, 7)), held, wanted)

    for bed in range(1, 7):
        clash = any(owner == bed and period.overlaps(wanted) for owner, period in held)
        assert (bed in free) is not clash
