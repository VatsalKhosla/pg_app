"""The map pins' rules (step 3.3, ADR 0029), without a database or Redis."""

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from app.core.geometry import Bounds
from app.core.money import Paise
from app.modules.search.domain.pins import cache_key, snapped
from app.modules.search.domain.query import SearchRequest

AREA = Bounds(south=28.60, west=77.15, north=28.70, east=77.25)


@given(
    st.floats(min_value=28.0, max_value=29.0),
    st.floats(min_value=77.0, max_value=78.0),
    st.floats(min_value=0.001, max_value=0.5),
    st.integers(min_value=5, max_value=20),
)
def test_a_snapped_area_holds_the_one_asked_for(
    south: float, west: float, size: float, zoom: int
) -> None:
    asked = Bounds(south=south, west=west, north=south + size, east=west + size)

    grown = snapped(asked, zoom)

    assert grown.south <= asked.south
    assert grown.west <= asked.west
    assert grown.north >= asked.north
    assert grown.east >= asked.east


def test_a_small_pan_asks_for_the_same_area() -> None:
    nudged = Bounds(south=28.6001, west=77.1502, north=28.7001, east=77.2502)

    assert snapped(nudged, 13) == snapped(AREA, 13)


def test_the_same_pins_share_a_key_and_any_difference_makes_another() -> None:
    def key(request: SearchRequest, **changes: object) -> str:
        options: dict[str, object] = {
            "area": AREA,
            "zoom": 13,
            "month": date(2027, 7, 1),
            "verified_only": True,
        } | changes
        return cache_key(request, **options)  # type: ignore[arg-type]

    plain = SearchRequest()
    assert key(plain) == key(SearchRequest(amenities=()))
    assert key(SearchRequest(amenities=("wifi", "cctv"))) == key(
        SearchRequest(amenities=("cctv", "wifi"))
    )
    others = {
        key(SearchRequest(budget_max=Paise(1_000_000))),
        key(SearchRequest(gender="girls")),
        key(SearchRequest(text="asha")),
        key(plain, zoom=14),
        key(plain, area=Bounds(south=28.5, west=77.15, north=28.7, east=77.25)),
        key(plain, month=date(2027, 8, 1)),
        key(plain, verified_only=False),
    }
    assert key(plain) not in others
    assert len(others) == 7
