"""The ops console's API end to end (step 2.4): an owner added, a listing built a step at a time,
published once it has a bed to sell, its photos in order, and every step in its history.

Listings here are fictional, placed by moving away from a seeded campus.
"""

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import event

from app.config import Settings
from app.core.actor import Role
from app.modules.media.domain.assets import AssetStatus
from tests.staff_api import Staff, run_as_staff, verify
from tests.staff_api import spot as _spot

pytestmark = pytest.mark.integration

Ops = Staff


@pytest.fixture
def run(make_settings: Callable[..., Settings], database_url: str) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Ops], Awaitable[Any]], *, role: Role = Role.OPS) -> Any:
        return run_as_staff(make_settings(database_url=database_url), scenario, role=role)

    return run_scenario


def test_an_owner_is_added_by_phone_and_found_by_phone_or_name(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        owner = await ops.owner()
        phone = owner["phone"]
        return {
            "owner": owner,
            "by phone": await ops.ok("GET", "/v1/ops/owners", params={"q": phone[3:]}),
            "by name": await ops.ok(
                "GET", "/v1/ops/owners", params={"q": owner["businessName"][-6:].upper()}
            ),
            "again": await ops.call(
                "POST",
                "/v1/ops/owners",
                json={"phone": phone, "legalName": "Another", "businessName": "Another"},
            ),
        }

    found = run(scenario)

    owner = found["owner"]
    assert owner["kycStatus"] == "not_started"
    assert owner["name"] == "A Fictional Owner"
    assert [item["id"] for item in found["by phone"]["items"]] == [owner["id"]]
    assert owner["id"] in [item["id"] for item in found["by name"]["items"]]
    assert found["again"].status_code == 409
    assert found["again"].json()["code"] == "OWNER_EXISTS"


CHARGES = [
    {
        "type": "metered",
        "kind": "electricity",
        "label": "Electricity",
        "ratePaise": 900,
        "unit": "kWh",
        "monthlyEstimatePaise": 80_000,
    },
    {"type": "monthly", "kind": "maintenance", "label": "Maintenance", "amountPaise": 50_000},
    {"type": "oneTime", "kind": "registration", "label": "Registration", "amountPaise": 100_000},
]


async def _with_a_room(
    ops: Ops, *, at: dict[str, float], name: str = "Fictional Residency"
) -> dict[str, Any]:
    """A listing with a double room category, its charges, and room 101 with two beds."""
    listing = await ops.listing(await ops.owner(), at=at, name=name)
    built = await ops.ok(
        "POST",
        f"/v1/ops/properties/{listing['id']}/room-categories",
        json={
            "occupancy": "double",
            "label": "Double sharing, AC",
            "ac": True,
            "baseRentPaise": 1_200_000,
            "ownerMinRentPaise": 1_100_000,
            "ownerMaxRentPaise": 1_500_000,
            "securityDepositPaise": 1_200_000,
            "mandatoryCharges": CHARGES,
        },
    )
    category_id = built["categories"][0]["id"]
    return await ops.ok(
        "POST",
        f"/v1/ops/room-categories/{category_id}/rooms",
        json={"label": "101", "floor": 1, "beds": 2},
    )


def test_a_listing_is_built_a_step_at_a_time(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        owner = await ops.owner()
        created = await ops.listing(owner, at=_spot(300))
        steps: dict[str, Any] = {
            "created": created,
            "twin": await ops.listing(owner, at=_spot(305)),
            "moved": await ops.ok(
                "PATCH",
                f"/v1/ops/properties/{created['id']}",
                json={"name": "Fictional Residency Annexe", "location": _spot(320)},
            ),
            "too soon": await ops.call(
                "POST", f"/v1/ops/properties/{created['id']}/status", json={"status": "published"}
            ),
        }
        built = await _with_a_room(ops, at=_spot(900))
        category = built["categories"][0]
        steps |= {
            "built": built,
            "third bed": await ops.call(
                "POST", f"/v1/ops/rooms/{category['rooms'][0]['id']}/beds", json={"label": "C"}
            ),
            "rent too high": await ops.call(
                "PATCH",
                f"/v1/ops/room-categories/{category['id']}",
                json={"baseRentPaise": 1_600_000},
            ),
        }
        return steps

    steps = run(scenario)

    created = steps["created"]
    assert created["status"] == "draft"
    assert created["nextStatuses"] == ["published", "delisted"]
    assert created["possibleDuplicates"] == []
    assert created["id"] in steps["twin"]["possibleDuplicates"]
    assert created["location"] == _spot(300)
    assert steps["moved"]["name"] == "Fictional Residency Annexe"
    assert steps["moved"]["location"] == _spot(320)
    assert steps["moved"]["displayLocation"] != created["displayLocation"]
    assert (steps["too soon"].status_code, steps["too soon"].json()["code"]) == (
        409,
        "LISTING_INCOMPLETE",
    )
    category = steps["built"]["categories"][0]
    assert category["monthlyChargesPaise"] == 130_000
    assert category["oneTimeChargesPaise"] == 100_000
    assert [charge["type"] for charge in category["mandatoryCharges"]] == [
        "metered",
        "monthly",
        "oneTime",
    ]
    assert [bed["label"] for bed in category["rooms"][0]["beds"]] == ["A", "B"]
    assert category["bedsPerRoom"] == 2
    assert (steps["third bed"].status_code, steps["third bed"].json()["code"]) == (
        409,
        "ROOM_FULL",
    )
    assert (steps["rent too high"].status_code, steps["rent too high"].json()["code"]) == (
        422,
        "LISTING_INVALID",
    )


def test_a_listing_is_published_with_its_photos_in_order_and_its_history_kept(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        # Its own name, to find it among every other test's live listings.
        name = f"Fictional Residency {secrets.token_hex(3)}"
        built = await _with_a_room(ops, at=_spot(1_000), name=name)
        listing_id = built["id"]
        photo, cover = await ops.media(), await ops.media()
        rejected = await ops.media(AssetStatus.REJECTED)
        unverified = await ops.call(
            "POST", f"/v1/ops/properties/{listing_id}/status", json={"status": "published"}
        )
        await verify(ops, built)
        return {
            "ids": {"listing": listing_id, "cover": cover, "photo": photo},
            "unverified": unverified,
            "amenities": await ops.ok(
                "PUT",
                f"/v1/ops/properties/{listing_id}/amenities",
                json={"amenities": ["wifi", "cctv"]},
            ),
            "media": await ops.ok(
                "PUT", f"/v1/ops/properties/{listing_id}/media", json={"media": [cover, photo]}
            ),
            "rejected media": await ops.call(
                "PUT", f"/v1/ops/properties/{listing_id}/media", json={"media": [rejected]}
            ),
            "published": await ops.ok(
                "POST", f"/v1/ops/properties/{listing_id}/status", json={"status": "published"}
            ),
            "live": await ops.ok(
                "GET", "/v1/ops/properties", params={"status": "published", "q": name}
            ),
            "history": await ops.ok("GET", f"/v1/ops/properties/{listing_id}/history"),
        }

    steps = run(scenario)

    ids = steps["ids"]
    # Not before a field agent has verified it (verified_only, on by default).
    assert (steps["unverified"].status_code, steps["unverified"].json()["detail"]) == (
        409,
        "needs a passed verification visit",
    )
    assert steps["amenities"]["amenities"] == ["cctv", "wifi"]
    assert [media["id"] for media in steps["media"]["media"]] == [ids["cover"], ids["photo"]]
    assert steps["media"]["media"][0]["renditions"][0]["url"].endswith("card.webp")
    assert steps["rejected media"].status_code == 422
    assert steps["published"]["status"] == "published"
    assert steps["published"]["nextStatuses"] == ["paused", "delisted"]
    assert steps["published"]["problems"] == []
    assert steps["published"]["publishedAt"] is not None
    live = {item["id"]: item for item in steps["live"]["items"]}
    assert live[ids["listing"]]["cover"]["id"] == ids["cover"]
    actions = [entry["action"] for entry in steps["history"]["items"]]
    assert actions[0] == "catalog.property_status_changed"
    assert {
        "catalog.property_created",
        "catalog.room_category_added",
        "catalog.room_added",
        "catalog.amenities_set",
        "catalog.media_set",
        "catalog.verification_scheduled",
        "catalog.verification_submitted",
    } <= set(actions)


def test_a_bed_out_of_use_leaves_nothing_to_sell(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> tuple[list[str], int, str]:
        listing = await ops.listing(await ops.owner(), at=_spot(600))
        built = await ops.ok(
            "POST",
            f"/v1/ops/properties/{listing['id']}/room-categories",
            json={
                "occupancy": "single",
                "label": "Single",
                "baseRentPaise": 1_500_000,
                "securityDepositPaise": 0,
            },
        )
        category_id = built["categories"][0]["id"]
        with_room = await ops.ok(
            "POST", f"/v1/ops/room-categories/{category_id}/rooms", json={"label": "1", "beds": 1}
        )
        bed_id = with_room["categories"][0]["rooms"][0]["beds"][0]["id"]
        stopped = await ops.ok("PATCH", f"/v1/ops/beds/{bed_id}", json={"status": "inactive"})
        refused = await ops.call(
            "POST", f"/v1/ops/properties/{listing['id']}/status", json={"status": "published"}
        )
        return stopped["problems"], refused.status_code, refused.json()["code"]

    problems, status, code = run(scenario)

    assert problems
    assert (status, code) == (409, "LISTING_INCOMPLETE")


def test_unknown_places_and_people_are_refused(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> list[tuple[int, str]]:
        owner = await ops.owner()
        good = {
            "owner": owner["id"],
            "locality": "kamla-nagar",
            "name": "Fictional Residency",
            "addressLine": "House 1, a fictional lane",
            "location": _spot(700),
            "locationPrecision": "exact",
            "genderPolicy": "coed",
            "meals": "none",
        }
        outcomes = []
        for change in (
            {"locality": "atlantis"},
            {"location": {"lat": 19.07, "lng": 72.87}},
            {"name": " "},
            {"genderPolicy": "everyone"},
        ):
            response = await ops.call("POST", "/v1/ops/properties", json=good | change)
            outcomes.append((response.status_code, response.json()["code"]))
        return outcomes

    assert run(scenario) == [
        (404, "NOT_FOUND"),
        (422, "LISTING_INVALID"),
        (422, "LISTING_INVALID"),
        (422, "VALIDATION_ERROR"),
    ]


def test_a_listing_reads_in_the_same_number_of_queries_however_many_rooms(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> tuple[int, int]:
        listing = await ops.listing(await ops.owner(), at=_spot(800))
        built = await ops.ok(
            "POST",
            f"/v1/ops/properties/{listing['id']}/room-categories",
            json={
                "occupancy": "triple",
                "label": "Triple",
                "baseRentPaise": 900_000,
                "securityDepositPaise": 900_000,
            },
        )
        category_id = built["categories"][0]["id"]
        statements = 0

        def count(*_: object) -> None:
            nonlocal statements
            statements += 1

        async def read() -> int:
            nonlocal statements
            statements = 0
            event.listen(ops.app.state.engine.sync_engine, "before_cursor_execute", count)
            try:
                await ops.ok("GET", f"/v1/ops/properties/{listing['id']}")
            finally:
                event.remove(ops.app.state.engine.sync_engine, "before_cursor_execute", count)
            return statements

        await ops.ok(
            "POST", f"/v1/ops/room-categories/{category_id}/rooms", json={"label": "1", "beds": 3}
        )
        few = await read()
        for label in ("2", "3", "4"):
            await ops.ok(
                "POST",
                f"/v1/ops/room-categories/{category_id}/rooms",
                json={"label": label, "beds": 3},
            )
        return few, await read()

    few, many = run(scenario)

    assert few == many


def test_field_agents_cant_build_listings(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> int:
        return (await ops.call("GET", "/v1/ops/properties")).status_code

    assert run(scenario, role=Role.FIELD_AGENT) == 403
