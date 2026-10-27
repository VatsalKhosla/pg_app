"""Search (step 3.2, ADR 0028): live listings found by where they are, the move-in month, the budget
and what they and their rooms offer; sorted, a page at a time, with distances from display points.

Every listing a test makes carries a word of its own, and its searches look for that word, so the
other tests' listings in the shared database never get in the way.
"""

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import event

from app.config import Settings
from app.core.geometry import Point, distance_m
from tests.flags import FixedFlags
from tests.jobs import run_due_jobs
from tests.staff_api import CAMPUS, Staff, run_as_staff, spot, verify

pytestmark = pytest.mark.integration

Ops = Staff
SEARCH = "/v1/search/properties"


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Ops], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


def _token() -> str:
    """A word only this test's listings have: twelve characters, so one typo still matches."""
    return f"zq{secrets.token_hex(5)}"


def _category(occupancy: str, rupees: int, *, beds: int, **features: bool) -> dict[str, Any]:
    return {
        "occupancy": occupancy,
        "label": f"{occupancy.title()} sharing",
        "baseRentPaise": rupees * 100,
        "securityDepositPaise": rupees * 100,
        "beds": beds,
        **features,
    }


async def _publish(
    ops: Ops,
    *,
    name: str,
    at: dict[str, float],
    categories: list[dict[str, Any]],
    locality: str = "kamla-nagar",
    gender: str = "girls",
    meals: str = "two",
    amenities: tuple[str, ...] = (),
    photo: bool = False,
    verified: bool = True,
) -> dict[str, Any]:
    """A listing built as ops build one, verified by a field agent unless not, and published."""
    owner = await ops.owner()
    listing = await ops.ok(
        "POST",
        "/v1/ops/properties",
        json={
            "owner": owner["id"],
            "locality": locality,
            "name": name,
            "addressLine": "House 1, a fictional lane",
            "location": at,
            "locationPrecision": "exact",
            "genderPolicy": gender,
            "meals": meals,
        },
    )
    path = f"/v1/ops/properties/{listing['id']}"
    for category in categories:
        fields = {key: value for key, value in category.items() if key != "beds"}
        built = await ops.ok("POST", f"{path}/room-categories", json=fields)
        added = next(each for each in built["categories"] if each["label"] == fields["label"])
        await ops.ok(
            "POST",
            f"/v1/ops/room-categories/{added['id']}/rooms",
            json={"label": "101", "beds": category["beds"]},
        )
    if amenities:
        await ops.ok("PUT", f"{path}/amenities", json={"amenities": list(amenities)})
    if photo:
        await ops.ok("PUT", f"{path}/media", json={"media": [await ops.media()]})
    if verified:
        await verify(ops, await ops.ok("GET", path))
    await ops.ok("POST", f"{path}/status", json={"status": "published"})
    return await ops.ok("GET", path)


async def _world(ops: Ops, token: str) -> dict[str, dict[str, Any]]:
    """Three live listings, published in this order:
    a, girls, two meals, Wi-Fi, a double AC room at ₹12,000, 500 m from campus, with a photo;
    b, boys, no meals, Wi-Fi and CCTV, a single with its own bath at ₹18,000, 1.5 km away;
    c, co-ed, three meals, in Vijay Nagar, a triple at ₹9,000 and a double AC at ₹13,000, 4 km.
    """
    a = await _publish(
        ops,
        name=f"Asha Girls PG {token}",
        at=spot(500, bearing=20),
        categories=[_category("double", 12_000, beds=2, ac=True)],
        amenities=("wifi",),
        photo=True,
    )
    b = await _publish(
        ops,
        name=f"Bhavna Boys PG {token}",
        at=spot(1_500, bearing=110),
        categories=[_category("single", 18_000, beds=1, attachedBath=True)],
        gender="boys",
        meals="none",
        amenities=("wifi", "cctv"),
    )
    c = await _publish(
        ops,
        name=f"Coed Stay {token}",
        at=spot(4_000, bearing=200),
        categories=[
            _category("triple", 9_000, beds=3),
            _category("double", 13_000, beds=2, ac=True),
        ],
        locality="vijay-nagar",
        gender="coed",
        meals="three",
    )
    await run_due_jobs(ops.app)
    return {"a": a, "b": b, "c": c}


async def _search(ops: Ops, **params: Any) -> dict[str, Any]:
    response = await ops.client.get(SEARCH, params=params)
    assert response.status_code == 200, response.text
    page: dict[str, Any] = response.json()
    return page


def _which(page: dict[str, Any], world: dict[str, dict[str, Any]]) -> list[str]:
    """The world's listings a page holds, by their letter, in the page's order."""
    letters = {listing["id"]: letter for letter, listing in world.items()}
    return [letters[item["id"]] for item in page["items"] if item["id"] in letters]


def test_each_filter_narrows_what_a_search_finds(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, list[str]]:
        token = _token()
        world = await _world(ops, token)
        near_a = world["a"]["displayLocation"]
        box = ",".join(
            f"{value:.6f}"
            for value in (
                near_a["lng"] - 0.002,
                near_a["lat"] - 0.002,
                near_a["lng"] + 0.002,
                near_a["lat"] + 0.002,
            )
        )
        searches: dict[str, dict[str, Any]] = {
            "everything": {},
            "within 3 km of campus": {"campus": "hindu-college", "radius_m": 3_000},
            "in Vijay Nagar": {"locality": "vijay-nagar"},
            "in a map area": {"bbox": box},
            "for girls": {"gender": "girls"},
            "single rooms": {"occupancy": "single"},
            "AC": {"ac": "true"},
            "an attached bath": {"attached_bath": "true"},
            "three meals": {"meals": "three"},
            "Wi-Fi": {"amenities": ["wifi"]},
            "Wi-Fi and CCTV": {"amenities": ["wifi", "cctv"]},
            "up to ₹10,000": {"budget_max_paise": 1_000_000},
            "₹15,000 or more": {"budget_min_paise": 1_500_000},
            "next month": {"move_in_month": "2027-08"},
            "a bed free": {"available": "true"},
        }
        return {
            name: sorted(_which(await _search(ops, q=token, sort="newest", **params), world))
            for name, params in searches.items()
        }

    assert run(scenario) == {
        "everything": ["a", "b", "c"],
        "within 3 km of campus": ["a", "b"],
        "in Vijay Nagar": ["c"],
        "in a map area": ["a"],
        "for girls": ["a"],
        "single rooms": ["b"],
        "AC": ["a", "c"],
        "an attached bath": ["b"],
        "three meals": ["c"],
        "Wi-Fi": ["a", "b"],
        "Wi-Fi and CCTV": ["b"],
        "up to ₹10,000": ["c"],
        "₹15,000 or more": ["b"],
        "next month": ["a", "b", "c"],
        "a bed free": ["a", "b", "c"],
    }


def test_a_card_shows_the_display_point_the_months_prices_and_distances(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        token = _token()
        world = await _world(ops, token)
        return {
            "world": world,
            "near campus": await _search(
                ops, q=token, campus="hindu-college", radius_m=5_000, sort="distance"
            ),
            "on a budget": await _search(ops, q=token, budget_max_paise=1_000_000),
            "no campus": await _search(ops, q=token),
            "headers": (await ops.client.get(SEARCH, params={"q": token})).headers,
        }

    found = run(scenario)

    world, page = found["world"], found["near campus"]
    cards = {letter: page["items"][index] for index, letter in enumerate(_which(page, world))}
    a, c = cards["a"], cards["c"]
    assert page["month"] == "2027-07-01"
    # The display point, and distances from it, never the building's exact point.
    assert a["displayLocation"] == world["a"]["displayLocation"]
    # PostGIS measures on the ellipsoid, distance_m on a sphere: within half a percent.
    shown = Point(**a["displayLocation"])
    assert abs(a["distanceM"] - distance_m(CAMPUS, shown)) <= distance_m(CAMPUS, shown) / 200
    assert a["nearestStation"]["slug"]
    assert a["nearestStation"]["distanceM"] > 0
    assert (a["minRentPaise"], a["maxRentPaise"]) == (1_200_000, 1_200_000)
    assert (a["verified"], a["licensed"], a["bedsFree"]) == (True, False, "few")
    assert a["cover"]["id"] == world["a"]["media"][0]["id"]
    assert a["cover"]["renditions"][0]["url"].endswith("card.webp")
    assert a["locality"] == {"slug": "kamla-nagar", "name": "Kamla Nagar"}
    # Both of c's categories, and with a budget only the one that fits it.
    assert (c["minRentPaise"], c["maxRentPaise"], c["bedsFree"]) == (900_000, 1_300_000, "some")
    [cheap] = [item for item in found["on a budget"]["items"] if item["id"] == world["c"]["id"]]
    assert (cheap["minRentPaise"], cheap["maxRentPaise"]) == (900_000, 900_000)
    assert all(item["distanceM"] is None for item in found["no campus"]["items"])
    assert found["headers"]["cache-control"] == "public, max-age=30"
    assert not {"addressLine", "location", "owner"} & set(a)


def test_sorts_and_pages_hold_together(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        token = _token()
        world = await _world(ops, token)
        orders = {
            sort: _which(await _search(ops, q=token, sort=sort), world)
            for sort in ("price_asc", "price_desc", "newest")
        }
        orders["distance"] = _which(
            await _search(ops, q=token, campus="hindu-college", radius_m=5_000, sort="distance"),
            world,
        )
        walked, cursor = [], None
        while True:
            params: dict[str, Any] = {"q": token, "sort": "price_asc", "limit": 1}
            if cursor is not None:
                params["cursor"] = cursor
            page = await _search(ops, **params)
            walked += _which(page, world)
            cursor = page["nextCursor"]
            if cursor is None:
                break
        first = await _search(ops, q=token, sort="price_asc", limit=1)
        other_sort = await ops.client.get(
            SEARCH, params={"q": token, "sort": "newest", "cursor": first["nextCursor"]}
        )
        made_up = await ops.client.get(SEARCH, params={"q": token, "cursor": "bm90IG1pbmU"})
        return {
            "orders": orders,
            "walked": walked,
            "other sort": (other_sort.status_code, other_sort.json()["code"]),
            "made up": (made_up.status_code, made_up.json()["code"]),
        }

    found = run(scenario)

    assert found["orders"] == {
        "price_asc": ["c", "a", "b"],
        "price_desc": ["b", "a", "c"],
        "newest": ["c", "b", "a"],
        "distance": ["a", "b", "c"],
    }
    # A page at a time, every listing once, in the same order.
    assert found["walked"] == ["c", "a", "b"]
    assert found["other sort"] == (422, "SEARCH_INVALID")
    assert found["made up"] == (422, "SEARCH_INVALID")


def test_text_search_puts_the_best_match_first_and_forgives_a_typo(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, list[str]]:
        token = _token()
        world = await _world(ops, token)
        typo = token[:-1] + ("0" if token[-1] != "0" else "1")
        return {
            # Recommended, with words to match: the listing that has them all comes first.
            "best match": _which(await _search(ops, q=f"bhavna {token}"), world)[:1],
            "typo": sorted(_which(await _search(ops, q=typo), world)),
        }

    assert run(scenario) == {"best match": ["b"], "typo": ["a", "b", "c"]}


def test_only_verified_listings_show_while_verified_only_is_on(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, list[str]]:
        token = _token()
        # Published while the flag was off, so it was allowed live unverified.
        ops.app.state.flags = FixedFlags(verified_only=False)
        world = {
            "d": await _publish(
                ops,
                name=f"Unverified Hall {token}",
                at=spot(2_000, bearing=300),
                categories=[_category("double", 11_000, beds=2)],
                verified=False,
            )
        }
        await run_due_jobs(ops.app)
        page = await ops.client.get(f"/v1/properties/{world['d']['slug']}")
        found = {
            # No visit has passed it, so its page has nothing to say about safety.
            "safety": [page.json()["safety"]],
            "flag off": _which(await _search(ops, q=token), world),
            "flag off, asked for all": _which(
                await _search(ops, q=token, verified_only="false"), world
            ),
        }
        ops.app.state.flags = FixedFlags(verified_only=True)
        found["flag on, asked for all"] = _which(
            await _search(ops, q=token, verified_only="false"), world
        )
        return found

    assert run(scenario) == {
        "safety": [None],
        "flag off": [],
        "flag off, asked for all": ["d"],
        "flag on, asked for all": [],
    }


def test_a_listing_leaves_search_while_paused_and_follows_its_changes(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, list[str]]:
        token = _token()
        listing = await _publish(
            ops,
            name=f"Fictional Residency {token}",
            at=spot(2_200, bearing=330),
            categories=[_category("double", 10_000, beds=2)],
        )
        world = {"e": listing}
        path = f"/v1/ops/properties/{listing['id']}"
        found = {}
        await run_due_jobs(ops.app)
        found["live"] = _which(await _search(ops, q=token), world)
        await ops.ok("POST", f"{path}/status", json={"status": "paused"})
        await run_due_jobs(ops.app)
        found["paused"] = _which(await _search(ops, q=token), world)
        await ops.ok("POST", f"{path}/status", json={"status": "published"})
        await ops.ok("PATCH", path, json={"name": f"Renamed Residency {token}"})
        await run_due_jobs(ops.app)
        found["renamed"] = _which(await _search(ops, q=f"renamed {token}"), world)
        return found

    assert run(scenario) == {"live": ["e"], "paused": [], "renamed": ["e"]}


def test_a_search_that_cant_be_answered_is_refused(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, tuple[int, str]]:
        searches: dict[str, dict[str, Any]] = {
            "two places": {"campus": "hindu-college", "locality": "kamla-nagar"},
            "by distance from nowhere": {"sort": "distance"},
            "no such campus": {"campus": "no-such-college"},
            "too far ahead": {"move_in_month": "2030-01"},
            "a box that isn't one": {"bbox": "1,2,3"},
            "an unknown parameter": {"colour": "blue"},
            "too many at once": {"limit": 51},
        }
        found = {}
        for name, params in searches.items():
            response = await ops.client.get(SEARCH, params=params)
            found[name] = (response.status_code, response.json()["code"])
        return found

    assert run(scenario) == {
        "two places": (422, "SEARCH_INVALID"),
        "by distance from nowhere": (422, "SEARCH_INVALID"),
        "no such campus": (422, "SEARCH_INVALID"),
        "too far ahead": (422, "SEARCH_INVALID"),
        "a box that isn't one": (422, "VALIDATION_ERROR"),
        "an unknown parameter": (422, "VALIDATION_ERROR"),
        "too many at once": (422, "VALIDATION_ERROR"),
    }


def test_a_search_takes_the_same_queries_however_many_it_finds(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> tuple[int, int]:
        token = _token()
        await _world(ops, token)
        statements = 0

        def count(*_: object) -> None:
            nonlocal statements
            statements += 1

        async def search(limit: int) -> int:
            nonlocal statements
            statements = 0
            event.listen(ops.app.state.engine.sync_engine, "before_cursor_execute", count)
            try:
                await _search(ops, q=token, campus="hindu-college", radius_m=5_000, limit=limit)
            finally:
                event.remove(ops.app.state.engine.sync_engine, "before_cursor_execute", count)
            return statements

        return await search(1), await search(3)

    one, three = run(scenario)

    assert one == three
