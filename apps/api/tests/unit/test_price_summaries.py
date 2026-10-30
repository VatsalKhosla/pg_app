"""Price summaries' rules (steps 3.1 and 4.7, ADRs 0027 and 0042), without a database."""

from datetime import UTC, date, datetime

from hypothesis import given
from hypothesis import strategies as st

from app.core.calendar import india_date
from app.core.money import Paise
from app.modules.search.domain.summaries import (
    SUMMARY_MONTHS,
    CategoryRent,
    months_from,
    summarise,
)


def test_summaries_cover_this_month_and_the_next_six() -> None:
    assert months_from(date(2027, 7, 14)) == [
        date(2027, 7, 1),
        date(2027, 8, 1),
        date(2027, 9, 1),
        date(2027, 10, 1),
        date(2027, 11, 1),
        date(2027, 12, 1),
        date(2028, 1, 1),
    ]


def test_the_months_run_on_past_a_new_year() -> None:
    assert months_from(date(2027, 12, 31), count=3) == [
        date(2027, 12, 1),
        date(2028, 1, 1),
        date(2028, 2, 1),
    ]


def test_the_month_is_indias() -> None:
    # 19:00 UTC on 31 January is already 1 February in India.
    assert months_from(india_date(datetime(2027, 1, 31, 19, 0, tzinfo=UTC)))[0] == date(2027, 2, 1)


def test_a_months_range_is_the_engines_and_an_unpriced_month_has_none() -> None:
    rents = [
        CategoryRent(
            category_id=7,
            base_rent=Paise(1_200_000),
            active_beds=2,
            occupancy="double",
            ac=True,
            attached_bath=False,
        )
    ]
    july, august, *_ = months_from(date(2027, 7, 14))

    summaries = summarise(
        rents,
        [july, august],
        {
            (7, july): (Paise(1_380_000), Paise(1_380_000)),
            (7, august): (Paise(1_140_000), Paise(1_200_000)),
        },
    )
    unpriced = summarise(rents, [july, august], {})

    assert [(s.month, s.min_rent, s.max_rent, s.available_beds) for s in summaries] == [
        (july, 1_380_000, 1_380_000, 2),
        (august, 1_140_000, 1_200_000, 2),
    ]
    assert unpriced == []


@given(
    st.lists(
        st.tuples(
            st.integers(min_value=1),
            st.integers(min_value=1, max_value=10_000_000),
            st.integers(min_value=1, max_value=4),
        ).map(
            lambda drawn: CategoryRent(drawn[0], Paise(drawn[1]), drawn[2], "double", False, True)
        ),
        max_size=6,
        unique_by=lambda rent: rent.category_id,
    ),
    st.dates(min_value=date(2026, 1, 1), max_value=date(2040, 12, 31)),
)
def test_every_priced_category_gets_every_month_and_a_sound_range(
    rents: list[CategoryRent], today: date
) -> None:
    months = months_from(today)
    # As the engine might price them: the listed rent, or up to a tenth below it.
    priced = {
        (rent.category_id, month): (Paise(max(rent.base_rent * 9 // 10, 1)), rent.base_rent)
        for rent in rents
        for month in months
    }
    summaries = summarise(rents, months, priced)

    assert len(months) == SUMMARY_MONTHS
    assert all(month.day == 1 for month in months)
    assert len({(summary.category_id, summary.month) for summary in summaries}) == len(rents) * len(
        months
    )
    assert all(0 < summary.min_rent <= summary.max_rent for summary in summaries)
