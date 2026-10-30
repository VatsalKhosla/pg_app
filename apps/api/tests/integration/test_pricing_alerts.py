"""Pricing's integrity alerts in the API (step 4.8, ADR 0043): seeded scenarios raise each alert
exactly once, however often the checks run; a rent alert resolves itself once the rent is no
longer below the market; and ops read and resolve alerts.

Each test's listings are in a locality of its own, and its assertions read only its own alerts:
the checks look at every listing in the shared database."""

import secrets
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.modules.catalog.models import Property
from app.modules.pricing.models import PricingAlert
from app.modules.pricing.service import AlertChecks
from tests.integration.test_pricing_quotes import _anyone, _rules
from tests.integration.test_search import _category, _publish
from tests.staff_api import NOW, Staff, run_as_staff, spot

pytestmark = pytest.mark.integration

ALERTS = "/v1/ops/pricing-alerts"
JULY = {
    "label": "July peak",
    "params": {"kind": "season", "start": "07-01", "end": "07-31", "bps": 1500},
}


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


async def _check(ops: Staff, check: str) -> None:
    """Run one of the checks, as the nightly job does, in a transaction of its own."""
    async with ops.app.state.sessionmaker() as db, db.begin():
        await getattr(AlertChecks(db, ops.app.state.clock), check)()


async def _alerts_of(ops: Staff, listing: dict[str, Any]) -> list[PricingAlert]:
    async with ops.app.state.sessionmaker() as db, db.begin():
        rows = await db.scalars(
            select(PricingAlert)
            .join(Property, Property.id == PricingAlert.property_id)
            .where(Property.slug == listing["slug"])
            .order_by(PricingAlert.id)
        )
        return list(rows)


def test_a_rent_far_below_its_market_is_raised_once_and_clears_itself(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        for rent in (10_000, 10_000, 12_000):
            await _publish(
                ops,
                name=f"Market PG {secrets.token_hex(4)}",
                at=spot(530),
                locality="mukherjee-nagar",
                categories=[_category("double", rent, beds=1)],
            )
        cheap = await _publish(
            ops,
            name=f"Cheap PG {secrets.token_hex(4)}",
            at=spot(540),
            locality="mukherjee-nagar",
            categories=[_category("double", 7_000, beds=1)],
        )
        room = cheap["categories"][0]["id"]
        for _ in range(2):
            await _check(ops, "market")
        seen: dict[str, Any] = {"twice": await _alerts_of(ops, cheap)}
        # ₹8,000 is within 25% of the ₹10,000 median: it clears itself.
        await ops.ok("PATCH", f"/v1/ops/room-categories/{room}", json={"baseRentPaise": 800_000})
        await _check(ops, "market")
        seen["fixed"] = await _alerts_of(ops, cheap)
        # A new rent that's too low again is a new alert.
        await ops.ok("PATCH", f"/v1/ops/room-categories/{room}", json={"baseRentPaise": 650_000})
        await _check(ops, "market")
        seen["again"] = await _alerts_of(ops, cheap)
        return seen

    seen = run(scenario)

    [alert] = seen["twice"]
    assert alert.kind == "rent_below_market"
    assert alert.resolved_at is None
    assert {key: alert.details[key] for key in ("listed_rent_paise", "median_rent_paise")} == {
        "listed_rent_paise": 700_000,
        "median_rent_paise": 1_000_000,
    }
    assert (alert.details["comparables"], alert.details["locality"]) == (3, "Mukherjee Nagar")
    [fixed] = seen["fixed"]
    assert fixed.resolved_at is not None
    assert (
        fixed.resolution
        == "The rent is no longer more than 25% below its market, or the room is no longer listed."
    )
    assert fixed.resolved_by is None
    first, second = seen["again"]
    assert first.resolved_at is not None
    assert (second.resolved_at, second.details["listed_rent_paise"]) == (None, 650_000)


def test_a_week_of_quotes_often_held_back_is_raised_once(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[PricingAlert]:
        listing = await _publish(
            ops,
            name=f"Clamped PG {secrets.token_hex(4)}",
            at=spot(550),
            locality="hudson-line",
            categories=[_category("double", 10_000, beds=2)],
        )
        room = listing["categories"][0]["id"]
        # July's peak asks ₹11,500, past the owner's ₹10,500: July's move-ins are held back.
        await ops.ok(
            "PATCH", f"/v1/ops/room-categories/{room}", json={"ownerMaxRentPaise": 1_050_000}
        )
        await _rules(ops, listing, JULY)
        move_ins = ["2027-07-20", "2027-07-25", "2027-07-30"] + [
            f"2027-08-{day:02d}" for day in (2, 4, 6, 8, 10, 12, 14)
        ]
        for move_in in move_ins:
            answer = await _anyone(
                ops.app,
                {"roomCategory": room, "moveIn": move_in, "stayMonths": 11},
                ip="203.0.113.40",
            )
            assert answer.status_code == 201, answer.text
        # The next week, the check looks at this one: 3 of 10 quotes held back.
        ops.app.state.clock.set(NOW + timedelta(days=7))
        for _ in range(2):
            await _check(ops, "clamps")
        return await _alerts_of(ops, listing)

    [alert] = run(scenario)

    assert alert.kind == "clamps_frequent"
    assert {key: alert.details[key] for key in ("week", "quotes", "clamped")} == {
        "week": "2027-07-12",
        "quotes": 10,
        "clamped": 3,
    }


def test_rules_that_keep_changing_are_raised_once_a_week_and_ops_resolve_it(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _publish(
            ops,
            name=f"Churning PG {secrets.token_hex(4)}",
            at=spot(560),
            locality="outram-lines",
            categories=[_category("double", 10_000, beds=2)],
        )
        seen: dict[str, Any] = {"after": []}
        # Each draft copies the rules in force, so each adds a season of its own month.
        for month in ("09", "10", "11", "12", "01"):
            await _rules(
                ops,
                listing,
                {
                    "label": f"Season {month}",
                    "params": {
                        "kind": "season",
                        "start": f"{month}-01",
                        "end": f"{month}-28",
                        "bps": 500,
                    },
                },
            )
            seen["after"].append(len(await _alerts_of(ops, listing)))
        [alert] = await _alerts_of(ops, listing)
        seen["details"] = alert.details
        page = await ops.ok("GET", ALERTS)
        seen["listed"] = [item for item in page["items"] if item["id"] == str(alert.public_id)]
        path = f"{ALERTS}/{alert.public_id}/resolve"
        seen["resolved"] = await ops.ok("POST", path, json={"note": "Owner trying prices."})
        seen["again"] = (await ops.call("POST", path, json={})).json()
        seen["open"] = await ops.ok("GET", ALERTS)
        seen["closed"] = await ops.ok("GET", ALERTS, params={"status": "resolved", "limit": 50})
        return seen

    seen = run(scenario)

    # Raised by the fourth activation of the week, and not again by the fifth.
    assert seen["after"] == [0, 0, 0, 1, 1]
    assert {key: seen["details"][key] for key in ("week", "activations")} == {
        "week": "2027-07-12",
        "activations": 4,
    }
    [listed] = seen["listed"]
    assert listed["kind"] == "rule_churn"
    assert listed["numbers"]["activations"] == 4
    assert listed["room"] is None
    resolved = seen["resolved"]
    assert (resolved["resolution"], resolved["resolvedBy"] is not None) == (
        "Owner trying prices.",
        True,
    )
    assert seen["again"]["code"] == "INVALID_TRANSITION"
    assert resolved["id"] not in {item["id"] for item in seen["open"]["items"]}
    assert resolved["id"] in {item["id"] for item in seen["closed"]["items"]}
