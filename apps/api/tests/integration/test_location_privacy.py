"""Location privacy and contact hiding (step 2.7, ADR 0026): the public sees a PG's display point,
never its exact point, its address or the owner's phone. Those show only to someone signed in,
while hide_owner_contact is off or once they're entitled (a visit, later a booking)."""

import json
import secrets
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from app.core.geometry import Point, distance_m
from app.modules.catalog.domain.location import MAX_OFFSET_M, MIN_OFFSET_M
from app.modules.catalog.repository import CatalogRepository
from app.modules.geo.reference import read_reference_data
from app.modules.identity.domain.sessions import SessionKind
from app.modules.media.domain.assets import AssetStatus, Moderation
from tests.authorization import MATRIX
from tests.flags import FixedFlags
from tests.jobs import run_due_jobs
from tests.staff_api import Staff, run_as_staff, sign_in, spot, verify

pytestmark = pytest.mark.integration

Ops = Staff
# Distinctive, so a response that carries it can't be missed.
ADDRESS = "House 47, a fictional lane behind the fictional market"


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Ops], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


async def _built(
    ops: Ops, *, at: dict[str, float], name: str = "Fictional Residency"
) -> dict[str, Any]:
    """A listing ops built: a double room category with room 101 and its two beds, and a photo."""
    owner = await ops.owner()
    listing = await ops.ok(
        "POST",
        "/v1/ops/properties",
        json={
            "owner": owner["id"],
            "locality": "kamla-nagar",
            "name": name,
            "addressLine": ADDRESS,
            "location": at,
            "locationPrecision": "exact",
            "genderPolicy": "girls",
            "meals": "two",
            "description": "A quiet, fictional PG.",
        },
    )
    path = f"/v1/ops/properties/{listing['id']}"
    built = await ops.ok(
        "POST",
        f"{path}/room-categories",
        json={
            "occupancy": "double",
            "label": "Double sharing",
            "baseRentPaise": 1_200_000,
            "securityDepositPaise": 1_200_000,
            "mandatoryCharges": [
                {"type": "monthly", "kind": "maintenance", "label": "Upkeep", "amountPaise": 50_000}
            ],
        },
    )
    await ops.ok(
        "POST",
        f"/v1/ops/room-categories/{built['categories'][0]['id']}/rooms",
        json={"label": "101", "beds": 2},
    )
    await ops.ok("PUT", f"{path}/amenities", json={"amenities": ["wifi"]})
    return await ops.ok("PUT", f"{path}/media", json={"media": [await ops.media()]})


async def _live(
    ops: Ops, *, at: dict[str, float], name: str = "Fictional Residency"
) -> tuple[dict[str, Any], str]:
    """A listing verified by a field agent and published: the listing, and the owner's phone."""
    built = await _built(ops, at=at, name=name)
    await verify(ops, built)
    published = await ops.ok(
        "POST", f"/v1/ops/properties/{built['id']}/status", json={"status": "published"}
    )
    return published, built["owner"]["phone"]


def _points(value: object) -> Iterator[Point]:
    """Every {lat, lng} anywhere in a JSON document."""
    if isinstance(value, dict):
        if isinstance(value.get("lat"), float) and isinstance(value.get("lng"), float):
            yield Point(lat=value["lat"], lng=value["lng"])
        for item in value.values():
            yield from _points(item)
    elif isinstance(value, list):
        for item in value:
            yield from _points(item)


def _leaks(body: str, *, exact: Point, phone_e164: str) -> list[str]:
    """What a response gives away: the address, the owner's phone, or a point near the building
    (the display point is at least 80 m away)."""
    found = []
    if ADDRESS.casefold() in body.casefold():
        found.append("the address")
    if phone_e164.removeprefix("+91") in body:
        found.append("the owner's phone")
    if f"{exact.lat:.5f}" in body and f"{exact.lng:.5f}" in body:
        found.append("the exact point's coordinates")
    try:
        document = json.loads(body)
    except ValueError:
        return found
    found += [
        f"a point {distance_m(point, exact):.0f} m from the building"
        for point in _points(document)
        if distance_m(point, exact) < MIN_OFFSET_M - 1
    ]
    return found


def _filled(path: str, *, slug: str, word: str) -> str:
    """A public route's path for the listing under test (or a campus); search looks for it."""
    if path == "/v1/search/properties":
        return f"{path}?q={word}&campus=hindu-college&radius_m=5000"
    if path == "/v1/map/pins":
        return f"{path}?q={word}&bbox=77.10,28.60,77.30,28.75&zoom=12"
    if "{" not in path:
        return path
    if path.startswith("/v1/properties/"):
        return path.format(slug=slug)
    if path.startswith("/v1/campuses/"):
        return path.format(slug=read_reference_data().campuses[0].slug)
    msg = f"teach the privacy sweep to fill in {path}"
    raise AssertionError(msg)


def test_no_public_route_gives_away_the_exact_point_the_address_or_the_owners_phone(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        at = spot(700, bearing=30)
        # A word of its own, for search to find it by among every other test's listings.
        word = f"sweep{secrets.token_hex(4)}"
        listing, owner_phone = await _live(ops, at=at, name=f"Fictional Residency {word}")
        # Its search entry, as the worker makes it.
        await run_due_jobs(ops.app)
        student = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        # Every route anyone may read, as anyone and as a student, and the contact route too.
        public = sorted(
            path
            for (method, path), rule in MATRIX.items()
            if method == "GET" and rule.expected["anonymous"] == 200
        )
        leaks: dict[str, list[str]] = {}
        shown_by: set[str] = set()
        for path in [*public, "/v1/properties/{slug}/contact"]:
            url = _filled(path, slug=listing["slug"], word=word)
            for who, response in (
                ("anyone", await ops.client.get(url)),
                ("a student", await student.call("GET", url)),
            ):
                if listing["id"] in response.text:
                    shown_by.add(path)
                found = _leaks(response.text, exact=Point(**at), phone_e164=owner_phone)
                if found:
                    leaks[f"{path} to {who} ({response.status_code})"] = found
        return {"public": public, "shown by": shown_by, "leaks": leaks}

    found = run(scenario)

    # The sweep sees the listing everywhere the public meets it, so a leak there would show.
    assert {"/v1/properties/{slug}", "/v1/search/properties", "/v1/map/pins"} <= found["shown by"]
    assert found["leaks"] == {}


def test_a_live_listing_shows_its_display_point_and_what_can_be_sold(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        built = await _built(ops, at=spot(900, bearing=200))
        path = f"/v1/ops/properties/{built['id']}"
        # A category without rooms, one taken out of use, and photos not ready to show.
        empty = await ops.ok(
            "POST",
            f"{path}/room-categories",
            json={
                "occupancy": "single",
                "label": "Single, no rooms yet",
                "baseRentPaise": 1_800_000,
                "securityDepositPaise": 1_800_000,
            },
        )
        retired = await ops.ok(
            "POST",
            f"{path}/room-categories",
            json={
                "occupancy": "triple",
                "label": "Triple sharing",
                "baseRentPaise": 900_000,
                "securityDepositPaise": 900_000,
            },
        )
        retired_id = next(
            category["id"]
            for category in retired["categories"]
            if category["label"] == "Triple sharing"
        )
        await ops.ok(
            "POST", f"/v1/ops/room-categories/{retired_id}/rooms", json={"label": "201", "beds": 3}
        )
        await ops.ok("PATCH", f"/v1/ops/room-categories/{retired_id}", json={"status": "inactive"})
        shown = built["media"][0]["id"]
        await ops.ok(
            "PUT",
            f"{path}/media",
            json={
                "media": [
                    shown,
                    await ops.media(AssetStatus.PROCESSING),
                    await ops.media(moderation=Moderation.PENDING),
                ]
            },
        )
        await verify(ops, built)
        await ops.ok("POST", f"{path}/status", json={"status": "published"})
        public = await ops.client.get(f"/v1/properties/{built['slug']}")
        return {
            "ops": await ops.ok("GET", path),
            "public": public.json(),
            "cache": public.headers["cache-control"],
            "empty": empty,
            "shown": shown,
        }

    found = run(scenario)

    public, ops = found["public"], found["ops"]
    assert public["displayLocation"] == ops["displayLocation"]
    exact, shown_at = Point(**ops["location"]), Point(**public["displayLocation"])
    assert MIN_OFFSET_M - 0.05 <= distance_m(exact, shown_at) <= MAX_OFFSET_M + 0.05
    assert (public["slug"], public["name"], public["verified"]) == (
        ops["slug"],
        "Fictional Residency",
        True,
    )
    assert public["ownerBusinessName"] == ops["owner"]["businessName"]
    assert public["locality"] == {"slug": "kamla-nagar", "name": "Kamla Nagar"}
    assert [amenity["slug"] for amenity in public["amenities"]] == ["wifi"]
    # Only the category with a bed to sell, with its money in paise and its charges totalled.
    [category] = public["categories"]
    assert (category["label"], category["baseRentPaise"], category["monthlyChargesPaise"]) == (
        "Double sharing",
        1_200_000,
        50_000,
    )
    # Only the photo that's processed and approved.
    assert [media["id"] for media in public["media"]] == [found["shown"]]
    # What the field agent found (tests/staff_api.py's checklist), and what's around it.
    assert public["safety"] == {
        "verifiedOn": "2027-07-14",
        "exits": 2,
        "fireExtinguishers": True,
        "cctv": True,
        "warden": True,
        "womenSafety": ["secure_entry", "woman_staff"],
    }
    assert (public["licenceStatus"], public["societyPermission"]) == ("unknown", "n/a")
    campuses = public["campusesNearby"]
    assert 1 <= len(campuses) <= 3
    assert [campus["distanceM"] for campus in campuses] == sorted(
        campus["distanceM"] for campus in campuses
    )
    assert all(campus["distanceM"] <= 5_000 for campus in campuses)
    assert len(public["stationsNearby"]) == 2
    assert set(public) >= {"description", "houseRules", "genderPolicy", "meals"}
    assert not {"addressLine", "location", "owner", "licenceNumber", "status"} & set(public)
    assert found["cache"] == "public, max-age=60"


def test_a_listing_the_public_may_not_see_isnt_there(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, int]:
        app = ops.app
        draft = await _built(ops, at=spot(1_100, bearing=300))
        paused, _ = await _live(ops, at=spot(1_300, bearing=120))
        await ops.ok("POST", f"/v1/ops/properties/{paused['id']}/status", json={"status": "paused"})
        # Published while only verified PGs weren't required, then the flag goes back on.
        app.state.flags = FixedFlags(verified_only=False)
        unverified = await _built(ops, at=spot(1_500, bearing=240))
        await ops.ok(
            "POST", f"/v1/ops/properties/{unverified['id']}/status", json={"status": "published"}
        )
        shown_while_off = (await ops.client.get(f"/v1/properties/{unverified['slug']}")).status_code
        app.state.flags = FixedFlags(verified_only=True)
        return {
            "draft": (await ops.client.get(f"/v1/properties/{draft['slug']}")).status_code,
            "paused": (await ops.client.get(f"/v1/properties/{paused['slug']}")).status_code,
            "unverified, flag off": shown_while_off,
            "unverified, flag on": (
                await ops.client.get(f"/v1/properties/{unverified['slug']}")
            ).status_code,
            "no such slug": (await ops.client.get("/v1/properties/no-such-pg")).status_code,
            "not a slug": (await ops.client.get("/v1/properties/Not%20A%20Slug")).status_code,
        }

    assert run(scenario) == {
        "draft": 404,
        "paused": 404,
        "unverified, flag off": 200,
        "unverified, flag on": 404,
        "no such slug": 404,
        "not a slug": 422,
    }


class _Visits:
    """Entitlements as the visits module will give them: these people, at these listings."""

    def __init__(self) -> None:
        self.booked: set[tuple[int, int]] = set()

    async def entitled(self, db: AsyncSession, *, user_id: int, property_id: int) -> bool:
        return (user_id, property_id) in self.booked


async def _property_id(ops: Ops, slug: str) -> int:
    async with ops.app.state.sessionmaker() as db, db.begin():
        found = await CatalogRepository(db).property_by_slug(slug)
        assert found is not None
        return found.id


async def _shown_to(ops: Ops, listing: dict[str, Any]) -> list[tuple[int | None, str]]:
    async with ops.app.state.sessionmaker() as db:
        rows = await db.scalars(
            select(AuditLog).where(
                AuditLog.action == "catalog.contact_shown", AuditLog.entity_id == listing["id"]
            )
        )
        return [(row.actor_id, row.details["because"]) for row in rows]


def test_contact_details_show_only_to_someone_allowed_and_each_time_is_audited(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        app = ops.app
        at = spot(1_700, bearing=75)
        listing, owner_phone = await _live(ops, at=at)
        contact = f"/v1/properties/{listing['slug']}/contact"
        visits = _Visits()
        app.state.contact_access = visits
        visitor = await sign_in(app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        browser = await sign_in(app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        anonymous = await ops.client.get(contact)
        hidden = await browser.call("GET", contact)
        visits.booked.add((visitor.user_id, await _property_id(ops, listing["slug"])))
        to_visitor = await visitor.call("GET", contact)
        # Until the founders' lawyer decides, the flag is on; with it off, anyone signed in sees.
        app.state.flags = FixedFlags(hide_owner_contact=False)
        flag_off = await browser.call("GET", contact)
        return {
            "anonymous": (anonymous.status_code, anonymous.json()["code"]),
            "hidden": (hidden.status_code, hidden.json()["code"]),
            "to visitor": to_visitor.json(),
            "flag off": flag_off.status_code,
            "owner phone": owner_phone,
            "at": at,
            "audit": await _shown_to(ops, listing),
            "users": (visitor.user_id, browser.user_id),
            "no-store": to_visitor.headers["cache-control"],
        }

    found = run(scenario)

    assert found["anonymous"] == (401, "UNAUTHENTICATED")
    assert found["hidden"] == (403, "CONTACT_HIDDEN")
    assert found["to visitor"] == {
        "ownerPhone": found["owner phone"],
        "addressLine": ADDRESS,
        "location": found["at"],
        "locationPrecision": "exact",
    }
    assert found["flag off"] == 200
    visitor, browser = found["users"]
    assert found["audit"] == [(visitor, "entitled"), (browser, "not_hidden")]
    assert found["no-store"] == "no-store"


def test_contact_lookups_are_limited_per_person(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> list[int]:
        listing, _ = await _live(ops, at=spot(1_900, bearing=160))
        ops.app.state.flags = FixedFlags(hide_owner_contact=False)
        student = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        contact = f"/v1/properties/{listing['slug']}/contact"
        return [(await student.call("GET", contact)).status_code for _ in range(31)]

    statuses = run(scenario)

    assert statuses[:30] == [200] * 30
    assert statuses[30] == 429


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("description", "Call the owner on 98765 43210 for a discount"),
        ("name", "Fictional Residency +91 98765 43210"),
        ("houseRules", ["Gate closes at 10 pm", "Warden: 9876543210"]),
    ],
)
def test_listing_text_can_carry_no_phone_number(
    run: Callable[..., Any], field: str, value: object
) -> None:
    async def scenario(ops: Ops) -> tuple[int, str]:
        built = await _built(ops, at=spot(2_100, bearing=10))
        response = await ops.call("PATCH", f"/v1/ops/properties/{built['id']}", json={field: value})
        return response.status_code, response.json()["detail"]

    status, detail = run(scenario)

    assert status == 422
    assert "can't include a phone number" in detail


def test_an_owners_business_name_can_carry_no_phone_number(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> tuple[int, str]:
        # The business name shows on the PG's page.
        owner = await ops.owner()
        response = await ops.call(
            "PATCH", f"/v1/ops/owners/{owner['id']}", json={"businessName": "Asha PG 98765 43210"}
        )
        return response.status_code, response.json()["detail"]

    status, detail = run(scenario)

    assert status == 422
    assert "can't include a phone number" in detail
