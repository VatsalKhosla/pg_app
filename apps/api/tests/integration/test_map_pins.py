"""Map pins (step 3.3, ADR 0029): every live listing in the map's area that matches the filters, as
a pin at its display point, at most 2,000, cached in Redis for a minute with an ETag.

The listings carry a word of their own, which every request filters by, so the other tests'
listings in the shared database never get in the way.
"""

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import event

from app.config import Settings
from app.core.geometry import Bounds, Point, distance_m
from app.modules.catalog.domain.location import MIN_OFFSET_M
from app.modules.search.domain.pins import snapped
from tests.integration.test_search import _category, _publish
from tests.jobs import run_due_jobs
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration

Ops = Staff
PINS = "/v1/map/pins"
# Fictional listings across Delhi: around North Campus, around South Campus, and between them.
PLACES = {
    "north": ({"lat": 28.6870, "lng": 77.2090}, "kamla-nagar"),
    "north-east": ({"lat": 28.6790, "lng": 77.2290}, "malka-ganj"),
    "south": ({"lat": 28.5880, "lng": 77.1700}, "satya-niketan"),
    "middle": ({"lat": 28.6320, "lng": 77.2190}, "malka-ganj"),
}


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Ops], Awaitable[Any]], **settings: Any) -> Any:
        options = {"database_url": database_url, "redis_url": valkey_url} | settings
        return run_as_staff(make_settings(**options), scenario)

    return run_scenario


async def _listings(ops: Ops, token: str) -> dict[str, dict[str, Any]]:
    built = {}
    for name, (at, locality) in PLACES.items():
        built[name] = await _publish(
            ops,
            name=f"Pin {name} {token}",
            at=at,
            locality=locality,
            gender="girls" if name == "north" else "coed",
            categories=[_category("double", 11_000, beds=2)],
        )
    await run_due_jobs(ops.app)
    return built


def _box(area: Bounds) -> str:
    return f"{area.west:.4f},{area.south:.4f},{area.east:.4f},{area.north:.4f}"


def test_a_pan_across_the_city_finds_every_listing_where_it_is(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        token = f"pin{secrets.token_hex(4)}"
        listings = await _listings(ops, token)
        ours = {listing["id"]: name for name, listing in listings.items()}
        seen: dict[str, list[tuple[Bounds, dict[str, Any]]]] = {}
        # A map area 0.05° square, panned in steps across south to north and west to east.
        steps = [round(28.55 + 0.05 * row, 2) for row in range(4)]
        for south in steps:
            for west in (77.10, 77.15, 77.20, 77.25):
                area = Bounds(south=south, west=west, north=south + 0.05, east=west + 0.05)
                response = await ops.client.get(
                    PINS, params={"bbox": _box(area), "zoom": 13, "q": token}
                )
                assert response.status_code == 200, response.text
                for pin in response.json()["pins"]:
                    if pin["id"] in ours:
                        seen.setdefault(ours[pin["id"]], []).append((area, pin))
        girls = await ops.client.get(
            PINS,
            params={"bbox": "77.10,28.55,77.30,28.75", "zoom": 11, "q": token, "gender": "girls"},
        )
        return {"listings": listings, "seen": seen, "girls": girls.json()["pins"]}

    found = run(scenario)

    listings, seen = found["listings"], found["seen"]
    assert set(seen) == set(PLACES)
    for name, sightings in seen.items():
        listing = listings[name]
        for area, pin in sightings:
            point = Point(lat=pin["lat"], lng=pin["lng"])
            # Its display point, never the exact one, inside the area as snapped to the zoom.
            assert (pin["lat"], pin["lng"]) == (
                listing["displayLocation"]["lat"],
                listing["displayLocation"]["lng"],
            )
            assert distance_m(point, Point(**listing["location"])) >= MIN_OFFSET_M - 0.05
            assert snapped(area, 13).contains(point)
            assert (pin["minRentPaise"], pin["maxRentPaise"], pin["bedsFree"]) == (
                1_100_000,
                1_100_000,
                "few",
            )
    assert [pin["id"] for pin in found["girls"]] == [listings["north"]["id"]]


def test_asking_again_is_answered_from_the_cache_with_the_same_etag(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        token = f"pin{secrets.token_hex(4)}"
        await _listings(ops, token)
        params: dict[str, str | int] = {"bbox": "77.15,28.65,77.25,28.72", "zoom": 13, "q": token}
        statements = 0

        def count(*_: object) -> None:
            nonlocal statements
            statements += 1

        engine = ops.app.state.engine.sync_engine
        answers = []
        for _ in range(2):
            statements = 0
            event.listen(engine, "before_cursor_execute", count)
            try:
                response = await ops.client.get(PINS, params=params)
            finally:
                event.remove(engine, "before_cursor_execute", count)
            answers.append((statements, response))
        etag = answers[0][1].headers["etag"]
        unchanged = await ops.client.get(PINS, params=params, headers={"If-None-Match": etag})
        filtered = await ops.client.get(PINS, params=params | {"gender": "boys"})
        return {"answers": answers, "unchanged": unchanged, "filtered": filtered, "etag": etag}

    found = run(scenario)

    (first_queries, first), (second_queries, second) = found["answers"]
    assert first_queries > 0
    # The second time, not one query: the answer came from Redis.
    assert second_queries == 0
    assert second.content == first.content
    assert second.headers["etag"] == found["etag"]
    assert first.headers["cache-control"] == "public, max-age=60"
    assert len(first.json()["pins"]) == 2
    assert (found["unchanged"].status_code, found["unchanged"].content) == (304, b"")
    assert found["unchanged"].headers["etag"] == found["etag"]
    assert found["filtered"].headers["etag"] != found["etag"]
    assert found["filtered"].json()["pins"] == []


def test_a_map_gets_2000_pins_at_most_and_is_told_there_were_more(
    run: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two, rather than seeding 2,001 listings: the cap works the same way at any size.
    monkeypatch.setattr("app.modules.search.service.PIN_CAP", 2)

    async def scenario(ops: Ops) -> dict[str, Any]:
        token = f"pin{secrets.token_hex(4)}"
        await _listings(ops, token)
        response = await ops.client.get(
            PINS, params={"bbox": "77.10,28.55,77.30,28.75", "zoom": 11, "q": token}
        )
        page: dict[str, Any] = response.json()
        return page

    found = run(scenario)

    assert len(found["pins"]) == 2
    assert found["truncated"] is True


def test_pins_still_come_while_redis_is_down(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> int:
        response = await ops.client.get(
            PINS, params={"bbox": "77.15,28.65,77.25,28.72", "zoom": 13}
        )
        return response.status_code

    # Nothing listens on port 9, the discard port.
    assert run(scenario, redis_url="redis://127.0.0.1:9/0") == 200


def test_a_map_without_an_area_or_outside_the_city_is_refused(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, tuple[int, str]]:
        asks: dict[str, dict[str, Any]] = {
            "no area": {"zoom": 13},
            "no zoom": {"bbox": "77.15,28.65,77.25,28.72"},
            "too close": {"bbox": "77.15,28.65,77.25,28.72", "zoom": 25},
            "Bengaluru": {"bbox": "77.5,12.9,77.6,13.0", "zoom": 13},
            "a campus too": {"bbox": "77.15,28.65,77.25,28.72", "zoom": 13, "campus": "x"},
        }
        found = {}
        for name, params in asks.items():
            response = await ops.client.get(PINS, params=params)
            found[name] = (response.status_code, response.json()["code"])
        return found

    assert run(scenario) == {
        "no area": (422, "VALIDATION_ERROR"),
        "no zoom": (422, "VALIDATION_ERROR"),
        "too close": (422, "VALIDATION_ERROR"),
        "Bengaluru": (422, "SEARCH_INVALID"),
        "a campus too": (422, "VALIDATION_ERROR"),
    }
