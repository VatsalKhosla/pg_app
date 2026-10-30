"""Ops' pricing editor in the API (step 4.6, ADR 0041): a version's preview is what a quote says
once that version is in force, and its chart is the price calendar's weeks, up to a year ahead,
with the limits that held each one back; the market beside a PG's rents is its band and the
middle of what its locality's other published PGs list.

Each test has a locality of its own, so bands and listings from other tests stay out of it."""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

import pytest

from app.config import Settings
from app.core.actor import Role
from app.core.calendar import india_date
from tests.integration.test_pricing_quotes import _anyone, _rules
from tests.integration.test_search import _category, _publish, _token
from tests.staff_api import NOW, Staff, run_as_staff, sign_in, spot

pytestmark = pytest.mark.integration

MOVE_IN = date(2027, 8, 20)
MINUS = chr(0x2212)
PEAK = {
    "label": "Peak season",
    "params": {"kind": "season", "start": "08-01", "end": "08-31", "bps": 1500},
}
EARLY = {"label": "Early-bird", "params": {"kind": "early_bird", "minDaysBefore": 30, "bps": -500}}
# What a student is shown, in a quote or in ops' preview of one.
STUDENT_SIDE = (
    "baseRentPaise",
    "monthlyRentPaise",
    "adjustments",
    "clamps",
    "explanation",
    "tokenPaise",
    "dueAtMoveInPaise",
    "depositPaise",
    "charges",
    "monthlyChargesPaise",
    "oneTimeChargesPaise",
)


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


def _student_side(priced: dict[str, Any]) -> dict[str, Any]:
    return {key: priced[key] for key in STUDENT_SIDE}


async def _unpublished(ops: Staff, locality: str, category: dict[str, Any]) -> None:
    """A listing being built, with one room category: no part of the market yet."""
    built = await ops.ok(
        "POST",
        "/v1/ops/properties",
        json={
            "owner": (await ops.owner())["id"],
            "locality": locality,
            "name": f"Unfinished PG {_token()}",
            "addressLine": "House 3, a fictional lane",
            "location": spot(480),
            "locationPrecision": "exact",
            "genderPolicy": "boys",
            "meals": "none",
        },
    )
    await ops.ok(
        "POST",
        f"/v1/ops/properties/{built['id']}/room-categories",
        json={key: value for key, value in category.items() if key != "beds"},
    )


def test_a_preview_is_what_a_quote_says_once_its_version_is_in_force(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        app = ops.app
        listing = await _publish(
            ops,
            name=f"Previewed PG {_token()}",
            at=spot(430),
            locality="shakti-nagar",
            categories=[_category("double", 10_000, beds=2)],
        )
        room = listing["categories"][0]["id"]
        active = await _rules(ops, listing, PEAK)
        draft = await ops.ok("POST", f"/v1/ops/properties/{listing['id']}/rule-sets/draft")
        await ops.ok("POST", f"/v1/ops/rule-sets/{draft['id']}/rules", json=EARLY)
        preview = f"/v1/ops/rule-sets/{draft['id']}/preview"
        query = {"room": room, "moveIn": MOVE_IN.isoformat(), "stay": 11}
        body = {"roomCategory": room, "moveIn": MOVE_IN.isoformat(), "stayMonths": 11}
        seen: dict[str, Any] = {
            "active": await ops.ok(
                "GET", f"/v1/ops/rule-sets/{active['id']}/preview", params=query
            ),
            "draft": await ops.ok("GET", preview, params=query),
            "quote now": (await _anyone(app, body, ip="203.0.113.30")).json(),
        }
        await ops.ok("POST", f"/v1/ops/rule-sets/{draft['id']}/activate", json={})
        seen["quote after"] = (await _anyone(app, body, ip="203.0.113.30")).json()
        seen["chart"] = await ops.ok("GET", f"/v1/ops/rule-sets/{draft['id']}/calendar")
        seen["calendar"] = await ops.ok("GET", f"/v1/properties/{listing['slug']}/price-calendar")

        # Up to a year ahead, beyond the booking horizon; never the past or later than that.
        today = india_date(NOW)
        seen["far"] = await ops.ok(
            "GET", preview, params=query | {"moveIn": (today + timedelta(days=200)).isoformat()}
        )
        for name, days in (("past", -1), ("too far", 367)):
            moved = (today + timedelta(days=days)).isoformat()
            seen[name] = (await ops.call("GET", preview, params=query | {"moveIn": moved})).json()
        other = await _publish(
            ops,
            name=f"Another PG {_token()}",
            at=spot(440),
            locality="shakti-nagar",
            categories=[_category("single", 12_000, beds=1)],
        )
        mismatched = query | {"room": other["categories"][0]["id"]}
        seen["other room"] = (await ops.call("GET", preview, params=mismatched)).status_code
        return seen

    seen = run(scenario)

    active, draft = seen["active"], seen["draft"]
    # The set in force previews as quotes say now, and the draft as they say once it's in force.
    assert _student_side(active) == _student_side(seen["quote now"])
    assert _student_side(draft) == _student_side(seen["quote after"])
    assert (active["monthlyRentPaise"], draft["monthlyRentPaise"]) == (1_150_000, 1_100_000)
    assert draft["explanation"] == (
        f"Base ₹10,000 · Peak season +15% · Early-bird {MINUS}5% = ₹11,000/month, fixed for"
        " your stay"
    )
    assert (draft["premiumBps"], draft["discountBps"], draft["bookableFrom"]) == (1500, 500, None)
    # The owner's fee is 30% of the listed rent, whatever the rules do, with GST (rule 2).
    assert {
        (priced["feePaise"], priced["gstPaise"], priced["ownerFeeTotalPaise"])
        for priced in (active, draft)
    } == {(300_000, 54_000, 354_000)}
    # Once in force, the version's chart is the PG page's calendar, week by week.
    calendar = seen["calendar"]["rooms"][0]
    chart = seen["chart"]["rooms"][0]
    assert [(week["moveIn"], week["monthlyRentPaise"]) for week in chart["weeks"]] == [
        (week["moveIn"], week["monthlyRentPaise"]) for week in calendar["weeks"]
    ]
    assert (chart["baseRentPaise"], chart["bedsFree"]) == (1_000_000, 2)
    # 200 days ahead: students can quote it from 120 days before.
    assert seen["far"]["bookableFrom"] == (india_date(NOW) + timedelta(days=80)).isoformat()
    assert seen["past"]["detail"] == "the move-in date has passed"
    assert seen["too far"]["detail"] == "the editor prices move-ins up to a year ahead"
    assert seen["other room"] == 404


def test_the_market_is_the_band_and_what_the_localitys_other_pgs_list(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        mine = await _publish(
            ops,
            name=f"Market PG {_token()}",
            at=spot(460),
            locality="roop-nagar",
            categories=[_category("double", 10_000, beds=2), _category("single", 15_000, beds=1)],
        )
        for rent in (12_500, 8_000, 9_000):
            await _publish(
                ops,
                name=f"Nearby PG {_token()}",
                at=spot(470),
                locality="roop-nagar",
                categories=[_category("double", rent, beds=1)],
            )
        # Not part of it: another occupancy, and a listing not yet published.
        await _publish(
            ops,
            name=f"Triples PG {_token()}",
            at=spot(475),
            locality="roop-nagar",
            categories=[_category("triple", 6_000, beds=3)],
        )
        await _unpublished(ops, "roop-nagar", _category("double", 1_000, beds=1))
        admin = await sign_in(ops.app, ops.client, Role.ADMIN)
        await admin.ok(
            "POST",
            "/v1/admin/rent-bands",
            json={
                "locality": "roop-nagar",
                "occupancy": "double",
                "minRentPaise": 700_000,
                "maxRentPaise": 1_100_000,
                "source": "internal",
                "reference": "Ops' read of the lane (fictional).",
            },
        )
        seen: dict[str, Any] = {
            "market": await ops.ok("GET", f"/v1/ops/properties/{mine['id']}/market")
        }
        # August's peak, which the band holds back for doubles; the chart says where.
        draft = await ops.ok("POST", f"/v1/ops/properties/{mine['id']}/rule-sets/draft")
        await ops.ok("POST", f"/v1/ops/rule-sets/{draft['id']}/rules", json=PEAK)
        chart = f"/v1/ops/rule-sets/{draft['id']}/calendar"
        seen["chart"] = await ops.ok("GET", chart)
        seen["next year"] = await ops.ok(
            "GET", chart, params={"from": "2028-06-26", "weeks": 12, "stay": 6}
        )
        return seen

    seen = run(scenario)

    market = seen["market"]
    assert market["locality"] == "Roop Nagar"
    # The defaults (PRODUCT_CONTEXT §9): other tests change them only from 400 days on.
    assert market["caps"] == {
        "maxPremiumBps": 4_000,
        "maxDiscountBps": 3_000,
        "roundingStepPaise": 5_000,
    }
    rooms = {room["label"]: room for room in market["rooms"]}
    double, single = rooms["Double sharing"], rooms["Single sharing"]
    # The middle of ₹8,000, ₹9,000 and ₹12,500: not this PG's own ₹10,000, nor the unpublished
    # ₹1,000.
    assert (double["medianRentPaise"], double["comparables"]) == (900_000, 3)
    assert double["band"] == {
        "minRentPaise": 700_000,
        "maxRentPaise": 1_100_000,
        "source": "internal",
        "reference": "Ops' read of the lane (fictional).",
    }
    assert (double["baseRentPaise"], double["ownerMinPaise"], double["ownerMaxPaise"]) == (
        1_000_000,
        None,
        None,
    )
    assert (single["band"], single["medianRentPaise"], single["comparables"]) == (None, None, 0)

    weeks = {room["label"]: room["weeks"] for room in seen["chart"]["rooms"]}
    august = [week for week in weeks["Double sharing"] if week["moveIn"].startswith("2027-08")]
    # ₹11,500 asked, held at the band's ₹11,000, and marked; singles have no band.
    assert [(week["monthlyRentPaise"], week["clamps"]) for week in august] == [
        (1_100_000, ["band_max"])
    ] * 4
    assert {
        week["monthlyRentPaise"]
        for week in weeks["Single sharing"]
        if week["moveIn"].startswith("2027-08")
    } == {1_725_000}
    assert all(
        week["clamps"] == []
        for week in weeks["Double sharing"]
        if not week["moveIn"].startswith("2027-08")
    )
    # Next summer, up to a year from today (14 July 2028).
    assert [week["moveIn"] for week in seen["next year"]["rooms"][0]["weeks"]] == [
        "2028-06-26",
        "2028-07-03",
        "2028-07-10",
    ]
    assert seen["next year"]["stayMonths"] == 6
