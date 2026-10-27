"""Search's rules (step 3.2, ADR 0028), without a database."""

import uuid
from datetime import date

import pytest

from app.core.geometry import Bounds
from app.core.money import Paise
from app.modules.search.domain.query import (
    BedsFree,
    Cursor,
    Order,
    SearchRequest,
    Sort,
    beds_free,
    decode_cursor,
    encode_cursor,
    order_for,
    request_problems,
)
from app.modules.search.domain.summaries import months_from

MONTHS = months_from(date(2027, 7, 14))


@pytest.mark.parametrize(
    ("has_text", "has_campus", "order"),
    [(True, True, Order.RELEVANCE), (False, True, Order.DISTANCE), (False, False, Order.NEWEST)],
)
def test_recommended_means_the_best_match_then_the_nearest_then_the_newest(
    has_text: bool, has_campus: bool, order: Order
) -> None:
    assert order_for(Sort.RECOMMENDED, has_text=has_text, has_campus=has_campus) is order


def test_a_sort_asked_for_is_the_order() -> None:
    assert order_for(Sort.PRICE_DESC, has_text=True, has_campus=True) is Order.PRICE_DESC


@pytest.mark.parametrize(
    ("request_", "problem"),
    [
        (
            SearchRequest(campus="hindu-college", locality="kamla-nagar"),
            "search around one place: a campus, a locality or a map area",
        ),
        (SearchRequest(sort=Sort.DISTANCE), "sorting by distance needs a campus"),
        (SearchRequest(radius_m=50), "the radius must be from 200 m to 15000 m"),
        (
            SearchRequest(budget_min=Paise(2_000_000), budget_max=Paise(1_000_000)),
            "the lowest budget is more than the highest",
        ),
        (
            SearchRequest(month=date(2028, 2, 1)),
            "prices are known for this month and the next six only",
        ),
        (
            SearchRequest(bbox=Bounds(south=28.7, west=77.3, north=28.6, east=77.2)),
            "the map area's west and south must be less than its east and north",
        ),
        (
            SearchRequest(bbox=Bounds(south=12.9, west=77.5, north=13.0, east=77.6)),
            "the map area must be inside Delhi NCR",
        ),
    ],
)
def test_a_search_that_cant_be_answered_says_why(request_: SearchRequest, problem: str) -> None:
    assert request_problems(request_, months=MONTHS) == [problem]


def test_an_ordinary_search_has_no_problems() -> None:
    request = SearchRequest(
        campus="hindu-college",
        month=date(2028, 1, 1),
        budget_min=Paise(800_000),
        budget_max=Paise(1_500_000),
        sort=Sort.DISTANCE,
    )

    assert request_problems(request, months=MONTHS) == []


@pytest.mark.parametrize("key", [1_200_000, 413.25, "2027-07-14T10:00:00+00:00"])
def test_a_cursor_comes_back_as_it_went(key: int | float | str) -> None:
    cursor = Cursor(order=Order.PRICE_ASC, key=key, after=uuid.uuid7())

    assert decode_cursor(encode_cursor(cursor)) == cursor


@pytest.mark.parametrize(
    "text",
    ["", "not-base64!", "WzEsMiwzXQ", encode_cursor(Cursor(Order.NEWEST, 1, uuid.uuid7()))[:-4]],
)
def test_anything_but_a_cursor_is_refused(text: str) -> None:
    assert decode_cursor(text) is None


@pytest.mark.parametrize(
    ("count", "bucket"),
    [
        (0, BedsFree.NONE),
        (1, BedsFree.FEW),
        (2, BedsFree.FEW),
        (3, BedsFree.SOME),
        (9, BedsFree.SOME),
        (10, BedsFree.MANY),
    ],
)
def test_free_beds_are_shown_roughly(count: int, bucket: BedsFree) -> None:
    assert beds_free(count) is bucket
