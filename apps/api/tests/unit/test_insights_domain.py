"""The owner's numbers (step 7.6, ADR 0063): whole basis points, nothing shown where there's
nothing to divide by."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.insights.domain.insights import BPS_PER_WHOLE, conversion_bps, taken_bps


@pytest.mark.parametrize(
    ("bookings", "visits", "bps"),
    [(0, 0, None), (3, 0, None), (0, 4, 0), (1, 4, 2_500), (1, 3, 3_333), (5, 4, 12_500)],
)
def test_conversion_is_bookings_for_each_visit_rounded_down(
    bookings: int, visits: int, bps: int | None
) -> None:
    assert conversion_bps(bookings, visits) == bps


@pytest.mark.parametrize(
    ("taken", "beds", "bps"),
    [(0, 0, None), (0, 4, 0), (1, 3, 3_333), (4, 4, 10_000), (5, 4, 10_000)],
)
def test_a_pg_is_never_more_than_full(taken: int, beds: int, bps: int | None) -> None:
    assert taken_bps(taken, beds) == bps


@given(st.integers(min_value=0, max_value=10_000), st.integers(min_value=1, max_value=10_000))
def test_full_never_passes_a_whole(taken: int, beds: int) -> None:
    bps = taken_bps(taken, beds)
    assert bps is not None
    assert 0 <= bps <= BPS_PER_WHOLE
