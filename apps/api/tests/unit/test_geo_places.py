"""The geo vocabulary (step 2.1): OpenStreetMap references, the NCR sanity box and distances."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.geo.domain.places import (
    EARTH_RADIUS_M,
    NCR_BOUNDS,
    OsmRef,
    OsmType,
    Point,
    distance_m,
)

# Points anywhere in the sanity box.
ncr_points = st.builds(
    Point,
    lat=st.floats(min_value=NCR_BOUNDS.south, max_value=NCR_BOUNDS.north),
    lng=st.floats(min_value=NCR_BOUNDS.west, max_value=NCR_BOUNDS.east),
)


def test_an_osm_reference_reads_and_prints_as_type_slash_id() -> None:
    ref = OsmRef.parse("relation/3859752")

    assert ref == OsmRef(OsmType.RELATION, 3859752)
    assert str(ref) == "relation/3859752"
    assert ref.url == "https://www.openstreetmap.org/relation/3859752"


@pytest.mark.parametrize(
    "raw", ["relation/0", "rel/1", "node/-5", "way/12a", "way/", " node/1", "node/1 ", "Node/1"]
)
def test_anything_else_is_not_an_osm_reference(raw: str) -> None:
    with pytest.raises(ValueError, match="not an OpenStreetMap element"):
        OsmRef.parse(raw)


def test_a_degree_of_latitude_is_a_degree_of_the_great_circle() -> None:
    one_degree = distance_m(Point(lat=28.0, lng=77.0), Point(lat=29.0, lng=77.0))

    assert one_degree == pytest.approx(math.pi * EARTH_RADIUS_M / 180)


@given(ncr_points, ncr_points)
def test_distance_is_symmetric_and_zero_to_itself(a: Point, b: Point) -> None:
    assert distance_m(a, a) == 0
    assert distance_m(a, b) == pytest.approx(distance_m(b, a))


@given(ncr_points, ncr_points, ncr_points)
def test_no_detour_is_shorter_than_the_direct_way(a: Point, b: Point, c: Point) -> None:
    assert distance_m(a, c) <= distance_m(a, b) + distance_m(b, c) + 1e-6


def test_the_ncr_box_holds_delhi_and_catches_swapped_coordinates() -> None:
    delhi = Point(lat=28.6328027, lng=77.2197713)  # OpenStreetMap's centre for relation/1942586

    assert NCR_BOUNDS.contains(delhi)
    assert not NCR_BOUNDS.contains(Point(lat=delhi.lng, lng=delhi.lat))
