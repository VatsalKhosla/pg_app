"""The geo refresh (step 2.1) against stand-ins for Nominatim and Wikidata, which answer from the
committed data: what it writes, what it refuses, and how politely it asks. No test calls the real
services."""

from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.modules.geo.domain.places import Point
from app.modules.geo.reference import (
    Locality,
    Manifest,
    MultiPolygon,
    dump_reference_data,
    read_reference_data,
)
from app.modules.geo.refresh import (
    MIN_INTERVAL_S,
    USER_AGENT,
    Fetcher,
    RefreshError,
    ResponseCache,
    Throttle,
    _boundary,
    _Geometry,
    _unchanged,
    http_client,
    refresh,
)

TODAY = date(2026, 10, 21)
DATA = read_reference_data()
CITY = DATA.cities[0]
LOCALITY = next(row for row in DATA.localities if row.boundary is not None)
# A campus that isn't the locality's own element (North Campus is both).
CAMPUS = next(row for row in DATA.campuses if row.osm != LOCALITY.osm)
STATION = next(row for row in DATA.metro_stations if len(row.lines) == 1)
LINE = next(line for line in DATA.metro_lines if line.slug == STATION.lines[0])

MANIFEST = Manifest.model_validate(
    {
        "cities": [{"slug": CITY.slug, "name": CITY.name, "osm": CITY.osm}],
        "localities": [
            {
                "slug": LOCALITY.slug,
                "city": LOCALITY.city,
                "name": LOCALITY.name,
                "osm": LOCALITY.osm,
            }
        ],
        "campuses": [
            {"slug": CAMPUS.slug, "city": CAMPUS.city, "name": CAMPUS.name, "osm": CAMPUS.osm}
        ],
        "metro_lines": [{"slug": LINE.slug, "name": LINE.name, "wikidata": LINE.wikidata}],
        "metro_stations": [{"slug": STATION.slug, "name": STATION.name, "osm": STATION.osm}],
    }
)


def _key(ref: str) -> str:
    kind, number = ref.split("/")
    return {"node": "N", "way": "W", "relation": "R"}[kind] + number


def _place(
    ref: str,
    point: Point,
    *,
    name: str,
    category: str = "place",
    kind: str = "suburb",
    tags: dict[str, str] | None = None,
    geojson: dict[str, Any] | None = None,
) -> dict[str, Any]:
    osm_type, osm_id = ref.split("/")
    return {
        "osm_type": osm_type,
        "osm_id": int(osm_id),
        "lat": str(point.lat),
        "lon": str(point.lng),
        "category": category,
        "type": kind,
        "name": name,
        "namedetails": {"name": name},
        "extratags": tags or {},
        **({} if geojson is None else {"geojson": geojson}),
    }


def _statement(value: object, *, rank: str = "normal", **qualifiers: date) -> dict[str, Any]:
    return {
        "mainsnak": {"snaktype": "value", "datavalue": {"value": value}},
        "rank": rank,
        "qualifiers": {
            prop: [
                {
                    "snaktype": "value",
                    "datavalue": {"value": {"time": f"+{day.isoformat()}T00:00:00Z"}},
                }
            ]
            for prop, day in qualifiers.items()
        },
    }


def _coordinates(point: Point) -> dict[str, float]:
    return {"latitude": point.lat, "longitude": point.lng}


def _outline(locality: Locality) -> dict[str, Any]:
    assert locality.boundary is not None
    polygon = locality.boundary.coordinates[0]
    return {
        "type": "Polygon",
        "coordinates": [[list(position) for position in ring] for ring in polygon],
    }


class FakeTime:
    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class FakeServices:
    """Nominatim's /lookup and Wikidata's wbgetentities, answering from the committed data."""

    def __init__(self, time: FakeTime) -> None:
        self.time = time
        self.requests: list[tuple[float, httpx.Request]] = []
        self.failures: list[httpx.Response] = []
        station_tags = {
            "station": "subway",
            "subway": "yes",
            "network": "Delhi Metro",
            "wikidata": STATION.wikidata,
        }
        self.places = {
            _key(CITY.osm): _place(CITY.osm, CITY.center.point, name=CITY.name),
            _key(LOCALITY.osm): _place(
                LOCALITY.osm,
                LOCALITY.center.point,
                name=LOCALITY.name,
                geojson=_outline(LOCALITY),
            ),
            _key(CAMPUS.osm): _place(
                CAMPUS.osm, CAMPUS.location.point, name=CAMPUS.name, category="amenity"
            ),
            _key(STATION.osm): _place(
                STATION.osm,
                STATION.location.point,
                name=STATION.name,
                category="railway",
                kind="station",
                tags=station_tags,
            ),
        }
        # Wikidata's position for the station, about 11 m north of OpenStreetMap's.
        near = Point(lat=STATION.location.lat + 0.0001, lng=STATION.location.lng)
        self.entities: dict[str, dict[str, Any]] = {
            STATION.wikidata: {
                "claims": {
                    "P81": [_statement({"id": LINE.wikidata})],
                    "P625": [_statement(_coordinates(near))],
                }
            },
            LINE.wikidata: {
                "labels": {"en": {"value": LINE.name}},
                # Wikidata writes colours without the # and in either case.
                "claims": {"P465": [_statement(LINE.colour[1:].lower())]},
            },
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((self.time.now, request))
        if self.failures:
            return self.failures.pop(0)
        if request.url.path == "/lookup":
            ids = request.url.params["osm_ids"].split(",")
            return httpx.Response(200, json=[self.places[key] for key in ids if key in self.places])
        if request.url.path == "/w/api.php":
            ids = request.url.params["ids"].split("|")
            return httpx.Response(
                200,
                json={"entities": {key: self.entities.get(key, {"missing": ""}) for key in ids}},
            )
        return httpx.Response(404)


@pytest.fixture
def time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def services(time: FakeTime) -> FakeServices:
    return FakeServices(time)


def _fetcher(services: FakeServices, time: FakeTime, cache: ResponseCache | None = None) -> Fetcher:
    return Fetcher(
        http_client(httpx.MockTransport(services.handle)),
        Throttle(monotonic=time.monotonic, sleep=time.sleep),
        sleep=time.sleep,
        cache=cache,
    )


def _problems(services: FakeServices, time: FakeTime) -> str:
    with pytest.raises(RefreshError) as refused:
        refresh(MANIFEST, fetcher=_fetcher(services, time), today=TODAY)
    return "\n".join(refused.value.problems)


def test_a_refresh_writes_what_openstreetmap_and_wikidata_say(
    services: FakeServices, time: FakeTime
) -> None:
    data, _ = refresh(MANIFEST, fetcher=_fetcher(services, time), today=TODAY)

    assert data.retrieved_on == TODAY
    assert data.cities == (CITY,)
    assert data.campuses == (CAMPUS,)
    assert data.metro_lines == (LINE,)
    assert data.metro_stations == (STATION,)
    assert data.localities[0].center == LOCALITY.center
    # Nominatim's Polygon, as the MultiPolygon the data keeps.
    assert LOCALITY.boundary is not None
    assert data.localities[0].boundary == MultiPolygon(
        type="MultiPolygon", coordinates=(LOCALITY.boundary.coordinates[0],)
    )


def test_it_asks_one_thing_a_second_saying_who_it_is_and_never_searches(
    services: FakeServices, time: FakeTime
) -> None:
    refresh(MANIFEST, fetcher=_fetcher(services, time), today=TODAY)

    moments = [moment for moment, _ in services.requests]
    requests = [request for _, request in services.requests]
    assert all(later - earlier >= MIN_INTERVAL_S for earlier, later in pairwise(moments))
    assert {request.headers["User-Agent"] for request in requests} == {USER_AGENT}
    assert {(request.url.host, request.url.path) for request in requests} == {
        ("nominatim.openstreetmap.org", "/lookup"),
        ("www.wikidata.org", "/w/api.php"),
    }
    wikidata = [request for request in requests if request.url.host == "www.wikidata.org"]
    assert {request.url.params["action"] for request in wikidata} == {"wbgetentities"}
    assert {request.url.params["maxlag"] for request in wikidata} == {"5"}


def test_a_mainline_station_is_refused(services: FakeServices, time: FakeTime) -> None:
    services.places[_key(STATION.osm)]["extratags"] = {
        "train": "yes",
        "network": "IR",
        "wikidata": STATION.wikidata,
    }

    assert "not a metro station" in _problems(services, time)


def test_an_element_nominatim_doesnt_have_is_refused(
    services: FakeServices, time: FakeTime
) -> None:
    del services.places[_key(CAMPUS.osm)]

    assert f"Nominatim has no {CAMPUS.osm}" in _problems(services, time)


def test_a_station_the_two_sources_place_apart_is_refused(
    services: FakeServices, time: FakeTime
) -> None:
    far = Point(lat=STATION.location.lat + 0.01, lng=STATION.location.lng)  # about 1.1 km
    services.entities[STATION.wikidata]["claims"]["P625"] = [_statement(_coordinates(far))]

    assert "m apart" in _problems(services, time)


def test_a_line_the_manifest_doesnt_list_comes_with_the_entry_to_add(
    services: FakeServices, time: FakeTime
) -> None:
    services.entities[STATION.wikidata]["claims"]["P81"].append(_statement({"id": "Q99999999"}))
    services.entities["Q99999999"] = {"labels": {"en": {"value": "Magenta Line"}}, "claims": {}}

    problems = _problems(services, time)

    assert '[[metro_lines]]\nslug = "magenta-line"' in problems
    assert 'wikidata = "Q99999999"' in problems


def test_lines_that_closed_or_have_not_opened_dont_count(
    services: FakeServices, time: FakeTime
) -> None:
    services.entities[STATION.wikidata]["claims"]["P81"] += [
        _statement({"id": "Q99999991"}, P582=TODAY - timedelta(days=1)),
        _statement({"id": "Q99999992"}, P580=TODAY + timedelta(days=1)),
        _statement({"id": "Q99999993"}, rank="deprecated"),
    ]

    data, _ = refresh(MANIFEST, fetcher=_fetcher(services, time), today=TODAY)

    assert data.metro_stations[0].lines == (LINE.slug,)


def test_a_busy_service_is_asked_again_after_the_wait_it_names(
    services: FakeServices, time: FakeTime
) -> None:
    services.failures = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, json={"error": {"code": "maxlag"}}, headers={"Retry-After": "5"}),
    ]

    refresh(MANIFEST, fetcher=_fetcher(services, time), today=TODAY)

    assert time.slept[:2] == [7.0, 5.0]


def test_it_gives_up_on_a_service_that_keeps_failing(
    services: FakeServices, time: FakeTime
) -> None:
    services.failures = [httpx.Response(503) for _ in range(10)]

    assert "answered 503" in _problems(services, time)


def test_a_second_run_takes_the_kept_answers(
    services: FakeServices, time: FakeTime, tmp_path: Path
) -> None:
    cache = ResponseCache(tmp_path)
    first, _ = refresh(MANIFEST, fetcher=_fetcher(services, time, cache), today=TODAY)
    asked = len(services.requests)

    again, _ = refresh(MANIFEST, fetcher=_fetcher(services, time, cache), today=TODAY)

    assert again == first
    assert len(services.requests) == asked


def test_answers_older_than_a_day_are_asked_for_again(
    services: FakeServices, time: FakeTime, tmp_path: Path
) -> None:
    refresh(MANIFEST, fetcher=_fetcher(services, time, ResponseCache(tmp_path)), today=TODAY)
    asked = len(services.requests)
    later = ResponseCache(tmp_path, now=lambda: 4_102_444_800.0)  # 2100-01-01

    refresh(MANIFEST, fetcher=_fetcher(services, time, later), today=TODAY)

    assert len(services.requests) == 2 * asked


def test_an_unchanged_refresh_leaves_the_file_alone(tmp_path: Path) -> None:
    path = tmp_path / "places.json"
    path.write_text(dump_reference_data(DATA), encoding="utf-8")
    renamed = DATA.model_copy(
        update={"cities": (CITY.model_copy(update={"name": "Renamed"}), *DATA.cities[1:])}
    )

    assert _unchanged(path, DATA.model_copy(update={"retrieved_on": TODAY + timedelta(days=9)}))
    assert not _unchanged(path, renamed)
    assert not _unchanged(tmp_path / "missing.json", DATA)


def test_outlines_become_multipolygons_and_rings_too_small_to_be_rings_go() -> None:
    assert LOCALITY.boundary is not None
    outer = [list(position) for position in LOCALITY.boundary.coordinates[0][0]]
    sliver = outer[:3]

    outline = _boundary(_Geometry(type="Polygon", coordinates=[outer, sliver]))

    assert outline is not None
    assert outline.coordinates == ((LOCALITY.boundary.coordinates[0][0],),)
    assert _boundary(None) is None
    assert _boundary(_Geometry(type="Point", coordinates=outer[0])) is None
    assert _boundary(_Geometry(type="Polygon", coordinates=[sliver])) is None
