"""Importing owners and their PGs (POST /v1/ops/listing-imports, ADR 0072): a check makes nothing,
an import makes owners and draft listings through the ops console's own services, and running the
same file again makes nothing twice. Every name, number and place here is fictional."""

from collections.abc import Callable
from typing import Any

import pytest

from app.config import Settings
from app.modules.catalog.domain.listing_import import COLUMNS
from tests.staff_api import Staff, phone, run_as_staff, spot

pytestmark = pytest.mark.integration

IMPORTS = "/v1/ops/listing-imports"


def _file(rows: list[dict[str, str]]) -> str:
    lines = [",".join(COLUMNS)]
    lines += [",".join(f'"{row.get(column, "")}"' for column in COLUMNS) for row in rows]
    return "\n".join(lines) + "\n"


def _rows() -> list[dict[str, str]]:
    owner, other = phone(), phone()
    here = spot(900)
    pinned = {
        "owner_name": "A Fictional Owner",
        "owner_phone": owner,
        "pg_name": f"Fictional Import House {owner[-4:]}",
        "locality": "kamla-nagar",
        "address": "House 3, a fictional lane",
        "latitude": str(here["lat"]),
        "longitude": str(here["lng"]),
        "gender": "girls",
        "meals": "three",
        "house_rules": "No pets",
        "amenities": "wifi; cctv",
    }
    return [
        pinned | {"room_type": "single", "rent": "18000", "deposit": "18000"},
        pinned | {"room_type": "double", "rent": "12,000", "deposit": "12000", "ac": "yes"},
        {
            "owner_name": "Another Fictional Owner",
            "owner_phone": other,
            "owner_email": f"owner-{other}@example.com",
            "pg_name": "Fictional Pinless House",
            "locality": "kamla-nagar",
            "address": "House 5, a fictional lane",
            "gender": "boys",
            "room_type": "double",
            "rent": "8000",
            "deposit": "8000",
        },
        {
            "owner_name": "Another Fictional Owner",
            "owner_phone": other,
            "pg_name": "Fictional Nowhere House",
            "locality": "nowhere-at-all",
            "address": "House 7, a fictional lane",
            "latitude": str(here["lat"]),
            "longitude": str(here["lng"]),
            "gender": "boys",
            "room_type": "single",
            "rent": "9000",
            "deposit": "9000",
        },
    ]


def _by_name(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {pg["name"].split(" House")[0]: pg for pg in report["pgs"]}


def test_ops_check_a_file_then_import_it_and_again_without_making_anything_twice(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> None:
    rows = _rows()
    csv = _file(rows)

    async def scenario(ops: Staff) -> dict[str, Any]:
        check = await ops.ok("POST", IMPORTS, json={"csv": csv, "dryRun": True})
        done = await ops.ok("POST", IMPORTS, json={"csv": csv, "dryRun": False})
        again = await ops.ok("POST", IMPORTS, json={"csv": csv, "dryRun": False})
        made = _by_name(done)["Fictional Import"]["listingId"]
        listing = await ops.ok("GET", f"/v1/ops/properties/{made}")
        return {"check": check, "done": done, "again": again, "listing": listing}

    seen = run_as_staff(make_settings(database_url=database_url, redis_url=valkey_url), scenario)

    check, done, again = (_by_name(seen[key]) for key in ("check", "done", "again"))
    assert seen["check"]["done"] is False
    # A check says what an import would make, and makes none of it.
    assert (check["Fictional Import"]["owner"], check["Fictional Import"]["listing"]) == (
        "new",
        "new",
    )
    assert check["Fictional Pinless"]["listing"] == "needs_pin"
    assert check["Fictional Nowhere"]["listing"] == "skipped"
    assert check["Fictional Nowhere"]["problems"] == ["no such locality: nowhere-at-all"]
    # The import: an owner and a draft with both room types; an owner whose PG waits for a pin;
    # and nothing for the PG in a place we don't know.
    imported = done["Fictional Import"]
    assert (imported["owner"], imported["listing"], imported["roomTypes"]) == ("new", "new", 2)
    assert imported["problems"] == []
    assert (done["Fictional Pinless"]["owner"], done["Fictional Pinless"]["listing"]) == (
        "new",
        "needs_pin",
    )
    assert done["Fictional Nowhere"]["listing"] == "skipped"
    listing = seen["listing"]
    assert listing["status"] == "draft"
    assert listing["locationPrecision"] == "approximate"
    assert sorted(category["occupancy"] for category in listing["categories"]) == [
        "double",
        "single",
    ]
    assert sorted(listing["amenities"]) == ["cctv", "wifi"]
    # Again: the owners are found by their phones, and the PG by its name.
    assert (again["Fictional Import"]["owner"], again["Fictional Import"]["listing"]) == (
        "existing",
        "exists",
    )
    assert again["Fictional Import"]["listingId"] == imported["listingId"]
    assert again["Fictional Pinless"]["owner"] == "existing"


def test_rows_it_cant_read_come_back_with_their_reasons(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> None:
    rows = [_rows()[0] | {"rent": "18,000 to 22,000"}]

    async def scenario(ops: Staff) -> dict[str, Any]:
        return await ops.ok("POST", IMPORTS, json={"csv": _file(rows), "dryRun": True})

    report = run_as_staff(make_settings(database_url=database_url, redis_url=valkey_url), scenario)

    assert report["pgs"] == []
    assert report["problems"] == ["Row 1: rent must be whole rupees, like 6000."]
