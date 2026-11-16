"""The owner's overview, month by month (ADR 0071): which months a stay counts in, and what it adds
up to."""

from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.insights.domain.owner import (
    Stay,
    booked_rent,
    living_on,
    month_starts,
    move_ins_by_month,
    next_month,
    rent_by_month,
)


def _stay(move_in: date, ends: date, rent: int = 1_000_000, months: int = 11) -> Stay:
    return Stay(move_in=move_in, ends=ends, monthly_rent_paise=rent, stay_months=months)


def test_the_months_end_with_this_one_and_cross_the_new_year() -> None:
    assert month_starts(date(2027, 2, 14), 4) == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
        date(2027, 2, 1),
    ]
    assert month_starts(date(2027, 1, 31), 1) == [date(2027, 1, 1)]
    assert next_month(date(2026, 12, 1)) == date(2027, 1, 1)


def test_a_stay_counts_in_every_month_it_was_lived_in_on_any_day() -> None:
    months = month_starts(date(2027, 4, 20), 5)  # December to April
    # From 31 December to 1 March: December, January and February, not March.
    stay = _stay(date(2026, 12, 31), date(2027, 3, 1), rent=900_000)

    assert rent_by_month([stay], months) == [900_000, 900_000, 900_000, 0, 0]
    assert move_ins_by_month([stay], months) == [1, 0, 0, 0, 0]


def test_tenants_in_the_same_month_add_up() -> None:
    months = month_starts(date(2027, 8, 10), 2)
    stays = [
        _stay(date(2027, 7, 1), date(2028, 6, 1), rent=1_000_000),
        _stay(date(2027, 8, 5), date(2028, 7, 5), rent=1_250_000),
    ]

    assert rent_by_month(stays, months) == [1_000_000, 2_250_000]
    assert move_ins_by_month(stays, months) == [1, 1]


def test_living_today_means_moved_in_and_not_yet_left() -> None:
    today = date(2027, 8, 10)
    stays = [
        _stay(date(2027, 7, 1), date(2028, 6, 1)),
        _stay(today, date(2028, 7, 1)),
        _stay(date(2026, 7, 1), today),  # left this morning
        _stay(today + timedelta(days=1), date(2028, 7, 1)),  # not in yet
    ]

    assert living_on(stays, today) == stays[:2]


def test_booked_rent_is_each_stay_for_all_its_months() -> None:
    stays = [
        _stay(date(2027, 7, 1), date(2028, 6, 1), rent=1_000_000, months=11),
        _stay(date(2027, 8, 1), date(2028, 2, 1), rent=800_000, months=6),
    ]

    assert booked_rent(stays) == 11_000_000 + 4_800_000
    assert booked_rent([]) == 0


days = st.dates(min_value=date(2025, 1, 1), max_value=date(2029, 12, 31))


@given(
    st.lists(st.tuples(days, st.integers(min_value=1, max_value=700)), max_size=12),
    days,
    st.integers(min_value=1, max_value=24),
)
def test_a_months_rent_is_exactly_the_stays_lived_in_that_month(
    raw: list[tuple[date, int]], today: date, count: int
) -> None:
    stays = [
        _stay(move_in, move_in + timedelta(days=length), rent=100 * (index + 1))
        for index, (move_in, length) in enumerate(raw)
    ]
    months = month_starts(today, count)

    rents = rent_by_month(stays, months)
    move_ins = move_ins_by_month(stays, months)

    assert len(rents) == len(move_ins) == count
    for first, rent, moved in zip(months, rents, move_ins, strict=True):
        end = next_month(first)
        lived = [
            stay
            for stay in stays
            if any(stay.on(first + timedelta(days=d)) for d in range((end - first).days))
        ]
        assert rent == sum(stay.monthly_rent_paise for stay in lived)
        assert moved == sum(1 for stay in stays if first <= stay.move_in < end)
