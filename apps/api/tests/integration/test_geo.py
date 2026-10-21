"""The geo reference data in PostGIS (step 2.1): loading it again and again, and the distances the
API serves from it. Done when a distance query from a campus returns sensible results."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event, func, select, text

from app.config import Settings
from app.core.audit import AuditLog
from app.core.clock import FrozenClock
from app.core.geometry import Point, distance_m
from app.main import create_app
from app.modules.geo.domain.places import NEARBY_RADIUS_M, NEAREST_STATIONS
from app.modules.geo.reference import ReferenceData, read_reference_data
from app.modules.geo.service import GeoReferenceLoader, LoadReport

pytestmark = pytest.mark.integration

DATA = read_reference_data()
type Scenario = Callable[[FastAPI, httpx.AsyncClient], Awaitable[Any]]


@pytest.fixture
def run(make_settings: Callable[..., Settings], database_url: str) -> Callable[..., Any]:
    """Run a scenario against the API, with the committed reference data loaded."""

    def run_scenario(scenario: Scenario) -> Any:
        app = create_app(
            make_settings(database_url=database_url),
            clock=FrozenClock(datetime(2027, 7, 14, 10, 0, tzinfo=UTC)),
        )

        async def wrapped() -> Any:
            async with app.router.lifespan_context(app):
                await _load(app, DATA)
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="https://api.test"
                ) as client:
                    return await scenario(app, client)

        return asyncio.run(wrapped())

    return run_scenario


async def _load(app: FastAPI, data: ReferenceData) -> LoadReport:
    async with app.state.sessionmaker() as db:
        return await GeoReferenceLoader(db, app.state.clock).load(data)


def _point(raw: dict[str, float]) -> Point:
    return Point(lat=raw["lat"], lng=raw["lng"])


def test_loading_the_same_data_again_changes_nothing(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, _client: httpx.AsyncClient) -> LoadReport:
        return await _load(app, DATA)

    again: LoadReport = run(scenario)

    assert not again.changed
    assert {kind.kind: kind.rows for kind in again.kinds} == {
        "cities": len(DATA.cities),
        "localities": len(DATA.localities),
        "campuses": len(DATA.campuses),
        "metro_lines": len(DATA.metro_lines),
        "metro_stations": len(DATA.metro_stations),
    }
    assert again.station_lines_changed == 0


def test_a_change_updates_its_row_and_the_log_says_which_data(run: Callable[..., Any]) -> None:
    locality = DATA.localities[0]
    station = next(row for row in DATA.metro_stations if len(row.lines) > 1)
    changed = DATA.model_copy(
        update={
            "localities": (locality.model_copy(update={"name": "Renamed"}), *DATA.localities[1:]),
            "metro_stations": tuple(
                row.model_copy(update={"lines": row.lines[:1]}) if row is station else row
                for row in DATA.metro_stations
            ),
        }
    )

    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> tuple[Any, ...]:
        report = await _load(app, changed)
        renamed = (await client.get("/v1/localities")).json()["items"]
        async with app.state.sessionmaker() as db:
            logged = await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "geo.reference_loaded")
                .where(AuditLog.entity_id == report.digest)
            )
        restored = await _load(app, DATA)
        return report, renamed, logged, restored

    report, renamed, logged, restored = run(scenario)

    updated = {kind.kind: kind.updated for kind in report.kinds}
    assert updated == {
        "cities": 0,
        "localities": 1,
        "campuses": 0,
        "metro_lines": 0,
        "metro_stations": 0,
    }
    assert report.station_lines_changed == len(station.lines) - 1
    assert {"slug": locality.slug, "name": "Renamed"}.items() <= next(
        item for item in renamed if item["slug"] == locality.slug
    ).items()
    assert logged == 1
    assert restored.changed


def test_each_campus_nearest_station_is_the_one_its_coordinates_say(
    run: Callable[..., Any],
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        response = await client.get("/v1/campuses")
        assert response.status_code == 200
        items: list[dict[str, Any]] = response.json()["items"]
        return items

    campuses = run(scenario)

    assert [campus["slug"] for campus in campuses] == [
        campus.slug for campus in sorted(DATA.campuses, key=lambda campus: campus.name.lower())
    ]
    for campus in campuses:
        here = _point(campus["location"])
        closest = min(DATA.metro_stations, key=lambda s: distance_m(here, s.location.point))
        nearest = campus["nearestStation"]
        assert nearest["station"]["slug"] == closest.slug, campus["slug"]
        # PostGIS measures on the ellipsoid, the check on a sphere: within half a percent.
        expected = distance_m(here, closest.location.point)
        assert nearest["distanceM"] == pytest.approx(expected, rel=0.005, abs=1)
        # Every campus seeded so far has a metro station within a short ride.
        assert nearest["distanceM"] < NEARBY_RADIUS_M


def test_from_sri_venkateswara_college_the_metro_is_a_short_walk(
    run: Callable[..., Any],
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await client.get("/v1/campuses/sri-venkateswara-college")
        assert response.status_code == 200
        body: dict[str, Any] = response.json()
        return body

    campus = run(scenario)

    stations = campus["stations"]
    assert len(stations) == NEAREST_STATIONS
    assert stations[0]["station"]["slug"] == "durgabai-deshmukh-south-campus"
    assert stations[0]["distanceM"] < 500
    assert stations[0]["station"]["lines"] == [
        {"slug": "pink", "name": "Pink Line", "colour": "#FF5872"}
    ]
    assert campus["nearestStation"] == stations[0]
    distances = [station["distanceM"] for station in stations]
    assert distances == sorted(distances)
    nearby = {item["locality"]["slug"]: item["distanceM"] for item in campus["localities"]}
    assert {"satya-niketan", "anand-niketan", "moti-bagh", "dhaula-kuan"} <= nearby.keys()
    assert "north-campus" not in nearby
    assert all(metres <= NEARBY_RADIUS_M for metres in nearby.values())


def test_north_campus_is_in_north_campus_and_satya_niketan_is_not_near_it(
    run: Callable[..., Any],
) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> dict[str, Any]:
        body: dict[str, Any] = (await client.get("/v1/campuses/du-north-campus")).json()
        return body

    campus = run(scenario)

    nearby = [item["locality"]["slug"] for item in campus["localities"]]
    assert nearby[0] == "north-campus"
    assert campus["localities"][0]["distanceM"] == 0
    assert {"kamla-nagar", "vijay-nagar", "malka-ganj"} <= set(nearby)
    assert "satya-niketan" not in nearby
    metres = [item["distanceM"] for item in campus["localities"]]
    assert metres == sorted(metres)


def test_every_locality_centre_lies_inside_its_boundary(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, _client: httpx.AsyncClient) -> list[str]:
        async with app.state.sessionmaker() as db:
            rows = await db.execute(
                text(
                    "SELECT slug FROM localities"
                    " WHERE boundary IS NOT NULL AND NOT ST_Covers(boundary, center)"
                )
            )
            return [slug for (slug,) in rows]

    assert run(scenario) == []


def test_the_lists_are_by_name_filtered_by_city_and_cacheable(run: Callable[..., Any]) -> None:
    async def scenario(_app: FastAPI, client: httpx.AsyncClient) -> dict[str, httpx.Response]:
        return {
            "cities": await client.get("/v1/cities"),
            "delhi": await client.get("/v1/localities", params={"city": "delhi"}),
            "noida": await client.get("/v1/localities", params={"city": "noida"}),
            "stations": await client.get("/v1/metro-stations"),
            "bad city": await client.get("/v1/campuses", params={"city": "Not A Slug"}),
            "unknown campus": await client.get("/v1/campuses/no-such-campus"),
        }

    responses = run(scenario)

    cities = responses["cities"].json()["items"]
    assert [city["name"] for city in cities] == sorted(
        (city.name for city in DATA.cities), key=str.lower
    )
    assert responses["cities"].headers["Cache-Control"] == "public, max-age=3600"
    delhi = [item["slug"] for item in responses["delhi"].json()["items"]]
    assert set(delhi) == {row.slug for row in DATA.localities if row.city == "delhi"}
    assert responses["noida"].json() == {"items": []}
    stations = {item["slug"]: item for item in responses["stations"].json()["items"]}
    assert [line["name"] for line in stations["kashmere-gate"]["lines"]] == [
        "Red Line",
        "Violet Line",
        "Yellow Line",
    ]
    assert responses["bad city"].status_code == 422
    assert responses["unknown campus"].status_code == 404
    assert responses["unknown campus"].json()["code"] == "NOT_FOUND"
    assert "no-store" in responses["unknown campus"].headers["Cache-Control"]


def test_each_list_takes_a_fixed_number_of_queries(run: Callable[..., Any]) -> None:
    async def scenario(app: FastAPI, client: httpx.AsyncClient) -> dict[str, int]:
        statements = 0

        def count(*_: object) -> None:
            nonlocal statements
            statements += 1

        counted: dict[str, int] = {}
        event.listen(app.state.engine.sync_engine, "before_cursor_execute", count)
        try:
            for path in (
                "/v1/cities",
                "/v1/localities",
                "/v1/campuses",
                "/v1/campuses/hindu-college",
                "/v1/metro-stations",
            ):
                statements = 0
                assert (await client.get(path)).status_code == 200
                counted[path] = statements
        finally:
            event.remove(app.state.engine.sync_engine, "before_cursor_execute", count)
        return counted

    # However many rows: the campus list reads the lines of every nearest station in one query,
    # and a campus page reads the campus, its stations, their lines and its localities.
    assert run(scenario) == {
        "/v1/cities": 1,
        "/v1/localities": 1,
        "/v1/campuses": 2,
        "/v1/campuses/hindu-college": 4,
        "/v1/metro-stations": 2,
    }
