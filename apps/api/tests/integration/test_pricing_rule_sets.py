"""Rule sets in the API (step 4.3, ADR 0038): a PG's first set drafted and activated; the next
drafted from it, refused while two seasons overlap, then activated in one step; the set before
archived and unchanged, so what it prices stays the same (rule 5); and the database itself
refusing to change a set that has been in force.

Quotes arrive in step 4.4; until then, "what a set prices" is the engine's quote from the set's
stored rules, which is what a quote will record."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.core.audit import AuditLog
from app.core.calendar import india_date
from app.core.money import rupees
from app.modules.pricing.domain.engine import PricingContext, quote
from app.modules.pricing.models import PricingRuleRow, PricingRuleSet
from app.modules.pricing.service import PolicyService, domain_rule
from tests.integration.test_search import _category, _publish, _token
from tests.staff_api import Staff, run_as_staff, spot

pytestmark = pytest.mark.integration

PEAK = {"kind": "season", "start": "06-01", "end": "08-31", "bps": 1500}
EARLY = {"kind": "early_bird", "minDaysBefore": 30, "bps": -500}
# A move-in in August, 37 days after the clock's day: in season, and early enough.
MOVE_IN = date(2027, 8, 20)


@pytest.fixture
def run(make_settings: Callable[..., Settings], database_url: str) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        return run_as_staff(make_settings(database_url=database_url), scenario)

    return run_scenario


async def _priced(ops: Staff, rule_set_id: str) -> tuple[int, list[str]]:
    """The double room's rent from the set's stored rules, and the rules that moved it."""
    app = ops.app
    async with app.state.sessionmaker() as db:
        policies = await PolicyService(db, app.state.clock).current()
        async with db.begin():
            found = await db.scalar(
                select(PricingRuleSet).where(PricingRuleSet.public_id == uuid.UUID(rule_set_id))
            )
            assert found is not None
            rows = await db.scalars(
                select(PricingRuleRow)
                .where(PricingRuleRow.rule_set_id == found.id)
                .order_by(PricingRuleRow.position)
            )
            rules = tuple(domain_rule(row) for row in rows)
    result = quote(
        PricingContext(
            room_category_id=0,
            base_rent_paise=rupees(10_000),
            owner_min_paise=None,
            owner_max_paise=None,
            move_in=MOVE_IN,
            stay_months=11,
            today=india_date(app.state.clock.now()),
            occupancy_bps=5_000,
            rules=rules,
            band=None,
            fee_policy=policies.fee,
            booking_policy=policies.booking,
            caps=policies.caps,
        )
    )
    return result.monthly_rent_paise, [item.label for item in result.adjustments]


async def _refused_by_the_database(ops: Staff, rule_set_id: str) -> list[str]:
    """What the database says to changing a set that has been in force, behind the API's back."""
    said = []
    for statement in (
        "UPDATE pricing_rules SET label = 'Changed' WHERE rule_set_id ="
        " (SELECT id FROM pricing_rule_sets WHERE public_id = :id)",
        "UPDATE pricing_rule_sets SET status = 'active' WHERE public_id = :id",
        "DELETE FROM pricing_rule_sets WHERE public_id = :id",
    ):
        async with ops.app.state.sessionmaker() as db:
            try:
                async with db.begin():
                    await db.execute(text(statement), {"id": uuid.UUID(rule_set_id)})
            except DBAPIError as error:
                said.append(str(error.orig).splitlines()[0])
    return said


def test_activating_a_new_version_never_changes_what_the_old_one_prices(  # noqa: PLR0915 - a set's whole life, in order
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _publish(
            ops,
            name=f"Rules PG {_token()}",
            at=spot(400),
            categories=[_category("double", 10_000, beds=2), _category("single", 14_000, beds=1)],
        )
        sets = f"/v1/ops/properties/{listing['id']}/rule-sets"
        double = next(item for item in listing["categories"] if item["label"] == "Double sharing")
        seen: dict[str, Any] = {}
        first = await ops.ok("POST", f"{sets}/draft")
        seen["first draft"] = first
        rules = f"/v1/ops/rule-sets/{first['id']}/rules"
        await ops.ok("POST", rules, json={"label": "Peak season", "params": PEAK})
        await ops.ok("POST", rules, json={"label": "Early-bird", "params": EARLY})
        seen["no change"] = (
            await ops.call("POST", rules, json={"label": "Nothing", "params": PEAK | {"bps": 0}})
        ).json()
        seen["not this PG's"] = (
            await ops.call(
                "POST",
                rules,
                json={
                    "label": "Elsewhere",
                    "params": EARLY,
                    "roomCategories": [str(uuid.uuid4())],
                },
            )
        ).json()
        v1 = await ops.ok(
            "POST", f"/v1/ops/rule-sets/{first['id']}/activate", json={"note": "Season one."}
        )
        seen["v1"] = v1
        seen["v1 prices"] = await _priced(ops, v1["id"])

        # The next version starts as a copy of the set in force.
        second = await ops.ok("POST", f"{sets}/draft")
        seen["v2 draft"] = second
        await ops.ok(
            "POST",
            f"/v1/ops/rule-sets/{second['id']}/rules",
            json={
                "label": "Admissions",
                "params": {"kind": "season", "start": "08-15", "end": "09-15", "bps": 1000},
                "roomCategories": [double["id"]],
            },
        )
        seen["overlap"] = (
            await ops.call("POST", f"/v1/ops/rule-sets/{second['id']}/activate", json={})
        ).json()
        drafted = await ops.ok("GET", f"/v1/ops/rule-sets/{second['id']}")
        seen["draft problems"] = drafted["problems"]
        admissions = next(rule for rule in drafted["rules"] if rule["label"] == "Admissions")
        await ops.ok(
            "PUT",
            f"/v1/ops/rules/{admissions['id']}",
            json={
                "label": "Admissions",
                "params": {"kind": "season", "start": "09-01", "end": "09-15", "bps": 1000},
                "roomCategories": [double["id"]],
            },
        )
        seen["v2"] = await ops.ok(
            "POST", f"/v1/ops/rule-sets/{second['id']}/activate", json={"note": "Admissions."}
        )
        seen["v1 after"] = await ops.ok("GET", f"/v1/ops/rule-sets/{v1['id']}")
        seen["v1 prices after"] = await _priced(ops, v1["id"])
        seen["versions"] = await ops.ok("GET", sets)

        # A set that has been in force stays as it was.
        kept_rule = seen["v1 after"]["rules"][0]["id"]
        seen["edit archived"] = (await ops.call("DELETE", f"/v1/ops/rules/{kept_rule}")).json()
        seen["reactivate"] = (
            await ops.call("POST", f"/v1/ops/rule-sets/{v1['id']}/activate", json={})
        ).json()
        seen["database"] = await _refused_by_the_database(ops, v1["id"])
        third = await ops.ok("POST", f"{sets}/draft")
        seen["discarded"] = (
            await ops.call("DELETE", f"/v1/ops/rule-sets/{third['id']}")
        ).status_code
        seen["discard archived"] = (
            await ops.call("DELETE", f"/v1/ops/rule-sets/{v1['id']}")
        ).json()
        async with ops.app.state.sessionmaker() as db:
            rows = await db.scalars(
                select(AuditLog.action)
                .where(AuditLog.entity_id == second["id"])
                .order_by(AuditLog.id)
            )
            seen["audit"] = list(rows)
        return seen

    seen = run(scenario)

    first = seen["first draft"]
    assert (first["version"], first["status"], first["rules"], first["problems"]) == (
        1,
        "draft",
        [],
        [],
    )
    assert seen["no change"]["code"] == "RULE_SET_INVALID"
    assert "a season moves the rent up or down" in seen["no change"]["detail"]
    assert "aren't this PG's" in seen["not this PG's"]["detail"]
    v1 = seen["v1"]
    assert (v1["version"], v1["status"], v1["note"]) == (1, "active", "Season one.")
    assert v1["activatedBy"] is not None
    assert [rule["label"] for rule in v1["rules"]] == ["Peak season", "Early-bird"]
    # ₹10,000 with 15% for the season and 5% off for booking early.
    assert seen["v1 prices"] == (rupees(11_000), ["Peak season", "Early-bird"])
    second = seen["v2 draft"]
    assert (second["version"], second["status"]) == (2, "draft")
    assert [rule["label"] for rule in second["rules"]] == ["Peak season", "Early-bird"]
    overlap = seen["overlap"]
    assert overlap["code"] == "RULE_SET_INVALID"
    expected = (
        "the seasons 'Peak season' and 'Admissions' both cover 08-15 for Double sharing:"
        " seasons may not overlap"
    )
    assert overlap["detail"] == expected
    assert seen["draft problems"] == [expected]
    v2 = seen["v2"]
    assert (v2["version"], v2["status"], v2["problems"]) == (2, "active", [])
    # The set before is archived as it was: same rules, same prices.
    v1_after = seen["v1 after"]
    assert v1_after["status"] == "archived"
    assert v1_after["archivedAt"] == v2["activatedAt"]
    assert v1_after["rules"] == v1["rules"]
    assert seen["v1 prices after"] == seen["v1 prices"]
    assert [
        (item["version"], item["status"], item["rules"]) for item in seen["versions"]["items"]
    ] == [
        (2, "active", 3),
        (1, "archived", 2),
    ]
    assert seen["edit archived"]["code"] == "INVALID_TRANSITION"
    assert seen["reactivate"]["code"] == "INVALID_TRANSITION"
    assert seen["database"] == [
        "the rules of an archived rule set never change",
        "an archived rule set only moves on to archived",
        "an archived rule set is kept",
    ]
    assert seen["discarded"] == 204
    assert seen["discard archived"]["code"] == "INVALID_TRANSITION"
    assert seen["audit"] == [
        "pricing.rule_set_drafted",
        "pricing.rule_added",
        "pricing.rule_changed",
        "pricing.rule_set_activated",
    ]
