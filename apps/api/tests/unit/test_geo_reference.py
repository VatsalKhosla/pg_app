"""The geo reference data as committed (step 2.1): what `make geo-refresh` makes of the manifest,
crediting OpenStreetMap, and refused when it doesn't hold together. The refused cases are the
committed data with one thing broken, so no test types in a coordinate."""

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.geo.reference import (
    DATA_PATH,
    Manifest,
    ReferenceData,
    dump_reference_data,
    manifest_differences,
    read_manifest,
    read_reference_data,
)

type Change = Callable[[dict[str, Any]], None]


def _committed() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return raw


def test_the_committed_data_is_what_a_refresh_made_of_the_manifest() -> None:
    assert manifest_differences(read_manifest(), read_reference_data()) == []


def test_the_committed_data_is_in_the_refresh_format_exactly() -> None:
    assert dump_reference_data(read_reference_data()) == DATA_PATH.read_text(encoding="utf-8")


def test_the_data_credits_openstreetmap_under_the_odbl() -> None:
    sources = {source.name: source for source in read_reference_data().sources}

    assert sources["OpenStreetMap"].licence == "ODbL-1.0"
    assert sources["OpenStreetMap"].attribution == "© OpenStreetMap contributors"
    assert sources["Wikidata"].licence == "CC0-1.0"


def test_every_line_serves_a_station_and_interchanges_keep_all_their_lines() -> None:
    data = read_reference_data()
    served = {line for station in data.metro_stations for line in station.lines}

    assert served == {line.slug for line in data.metro_lines}
    assert any(len(station.lines) > 1 for station in data.metro_stations)


def test_a_change_to_the_manifest_shows_until_the_data_is_refreshed() -> None:
    manifest = read_manifest()
    renamed = manifest.model_copy(
        update={
            "campuses": (
                manifest.campuses[0].model_copy(update={"name": "Renamed"}),
                *manifest.campuses[1:],
            )
        }
    )

    assert manifest_differences(renamed, read_reference_data()) == ["campuses"]


def _duplicate_slug(raw: dict[str, Any]) -> None:
    raw["campuses"].append(copy.deepcopy(raw["campuses"][0]))


def _unknown_city(raw: dict[str, Any]) -> None:
    raw["localities"][0]["city"] = "atlantis"


def _unknown_line(raw: dict[str, Any]) -> None:
    raw["metro_stations"][0]["lines"] = ["no-such-line"]


def _no_line(raw: dict[str, Any]) -> None:
    raw["metro_stations"][0]["lines"] = []


def _line_twice(raw: dict[str, Any]) -> None:
    station = raw["metro_stations"][0]
    station["lines"] = [station["lines"][0], station["lines"][0]]


def _swapped(raw: dict[str, Any]) -> None:
    point = raw["campuses"][0]["location"]
    point["lat"], point["lng"] = point["lng"], point["lat"]


def _open_ring(raw: dict[str, Any]) -> None:
    outlined = next(row for row in raw["localities"] if row["boundary"] is not None)
    outlined["boundary"]["coordinates"][0][0].pop()


def _extra_field(raw: dict[str, Any]) -> None:
    raw["cities"][0]["population"] = 1


def _lower_case_colour(raw: dict[str, Any]) -> None:
    raw["metro_lines"][0]["colour"] = raw["metro_lines"][0]["colour"].lower()


def _bad_osm(raw: dict[str, Any]) -> None:
    raw["cities"][0]["osm"] = "relation/one"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_duplicate_slug, "slugs used twice"),
        (_unknown_city, "in a city that isn't listed"),
        (_unknown_line, "lines that aren't listed"),
        (_no_line, "at least 1 item"),
        (_line_twice, "a line is listed twice"),
        (_swapped, "outside Delhi NCR"),
        (_open_ring, "ends where it starts"),
        (_extra_field, "Extra inputs are not permitted"),
        (_lower_case_colour, "String should match pattern"),
        (_bad_osm, "String should match pattern"),
    ],
)
def test_data_that_doesnt_hold_together_is_refused(change: Change, message: str) -> None:
    raw = _committed()
    change(raw)

    with pytest.raises(ValidationError, match=message):
        ReferenceData.model_validate(raw)


def test_a_manifest_naming_one_wikidata_line_twice_is_refused() -> None:
    raw = read_manifest().model_dump(mode="json")
    raw["metro_lines"].append({**raw["metro_lines"][0], "slug": "another"})

    with pytest.raises(ValidationError, match="Wikidata items used twice"):
        Manifest.model_validate(raw)
