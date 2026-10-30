"""Quotes in the API (step 4.4, ADR 0039): a quote's numbers are the engine's for the same inputs,
rebuilt from the database, and so is its digest; it stands 30 minutes and a booking then can't
take it; a new version of the rules never changes it; and what can't be quoted is refused."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.core.actor import Role
from app.core.calendar import india_date
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER
from app.core.csrf import issue_csrf_token
from app.core.money import Paise
from app.modules.identity.domain.sessions import SessionKind
from app.modules.pricing.domain.engine import PricingContext, quote
from app.modules.pricing.domain.quotes import inputs_digest
from app.modules.pricing.errors import QuoteExpiredError
from app.modules.pricing.models import PriceQuote, PricingRuleRow
from app.modules.pricing.service import PolicyService, QuoteLookup, domain_rule
from tests.conftest import TEST_SECRET_KEY
from tests.integration.test_search import _category, _publish, _token
from tests.staff_api import NOW, Staff, run_as_staff, sign_in, spot

pytestmark = pytest.mark.integration

QUOTES = "/v1/quotes"
MOVE_IN = date(2027, 8, 20)
MINUS = chr(0x2212)


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


async def _anyone(
    app: FastAPI, body: dict[str, Any], *, ip: str = "203.0.113.20"
) -> httpx.Response:
    """A quote asked for by someone signed out, from ``ip``."""
    csrf = issue_csrf_token(TEST_SECRET_KEY.encode(), None)
    transport = httpx.ASGITransport(app=app, client=(ip, 50_000))
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        return await client.post(
            QUOTES, json=body, headers={CSRF_HEADER: csrf, "Cookie": f"{CSRF_COOKIE}={csrf}"}
        )


async def _rules(ops: Staff, listing: dict[str, Any], *rules: dict[str, Any]) -> dict[str, Any]:
    """A new version of the PG's rules, with ``rules`` added to the one in force, activated."""
    draft = await ops.ok("POST", f"/v1/ops/properties/{listing['id']}/rule-sets/draft")
    for rule in rules:
        await ops.ok("POST", f"/v1/ops/rule-sets/{draft['id']}/rules", json=rule)
    return await ops.ok("POST", f"/v1/ops/rule-sets/{draft['id']}/activate", json={})


async def _as_the_engine_would(app: FastAPI, quote_id: str) -> tuple[Any, str, PriceQuote]:
    """The quote's own row, and the engine's answer and digest for the same inputs, rebuilt
    from the database: the rules of the set it names, the policies in force, no band."""
    async with app.state.sessionmaker() as db:
        policies = await PolicyService(db, app.state.clock).current()
        async with db.begin():
            row = await db.scalar(
                select(PriceQuote).where(PriceQuote.public_id == uuid.UUID(quote_id))
            )
            assert row is not None
            assert row.rule_set_id is not None
            rule_rows = await db.scalars(
                select(PricingRuleRow)
                .where(PricingRuleRow.rule_set_id == row.rule_set_id)
                .order_by(PricingRuleRow.position)
            )
            rules = tuple(domain_rule(rule) for rule in rule_rows)
    context = PricingContext(
        room_category_id=row.room_category_id,
        base_rent_paise=Paise(row.base_rent_paise),
        owner_min_paise=None,
        owner_max_paise=None,
        move_in=row.move_in,
        stay_months=row.stay_months,
        today=india_date(NOW),
        occupancy_bps=0,
        rules=rules,
        band=None,
        fee_policy=policies.fee,
        booking_policy=policies.booking,
        caps=policies.caps,
    )
    versions = {
        "rule_set": row.rule_set_id,
        "fee_policy": row.fee_policy_id,
        "booking_policy": row.booking_policy_id,
        "pricing_caps": row.pricing_caps_id,
        "rent_band": row.rent_band_id,
        "engine": row.engine_version,
    }
    return quote(context), inputs_digest(context, versions=versions), row


def test_a_quote_is_the_engines_answer_kept_for_thirty_minutes(  # noqa: PLR0915 - one quote's life, in order
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        app = ops.app
        listing = await _publish(
            ops,
            name=f"Quoted PG {_token()}",
            at=spot(400),
            categories=[_category("double", 10_000, beds=2)],
        )
        category = listing["categories"][0]["id"]
        await _rules(
            ops,
            listing,
            {
                "label": "Peak season",
                "params": {"kind": "season", "start": "06-01", "end": "08-31", "bps": 1500},
            },
            {
                "label": "Early-bird",
                "params": {"kind": "early_bird", "minDaysBefore": 30, "bps": -500},
            },
        )
        body = {"roomCategory": category, "moveIn": MOVE_IN.isoformat(), "stayMonths": 11}
        seen: dict[str, Any] = {}
        asked = await _anyone(app, body)
        seen["status"] = asked.status_code
        seen["quote"] = asked.json()
        seen["engine"] = await _as_the_engine_would(app, seen["quote"]["id"])
        student = await sign_in(app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        mine = await student.ok("POST", QUOTES, json=body)
        async with app.state.sessionmaker() as db:
            seen["asked by"] = await db.scalar(
                select(PriceQuote.user_id).where(PriceQuote.public_id == uuid.UUID(mine["id"]))
            )
        seen["student"] = student.user_id

        # A new version of the rules prices new quotes, and leaves this one as it was.
        await _rules(
            ops,
            listing,
            {
                "label": "Long stay",
                "params": {"kind": "length_of_stay", "tiers": [{"minMonths": 6, "bps": -300}]},
            },
        )
        seen["again"] = await ops.ok("GET", f"{QUOTES}/{seen['quote']['id']}")
        seen["new"] = (await _anyone(app, body)).json()
        async with app.state.sessionmaker() as db:
            try:
                async with db.begin():
                    await db.execute(
                        text(
                            "UPDATE price_quotes SET monthly_rent_paise = 1 WHERE public_id = :id"
                        ),
                        {"id": uuid.UUID(seen["quote"]["id"])},
                    )
            except DBAPIError as error:
                seen["database"] = str(error.orig).splitlines()[0]

        # Refused: the past, beyond the horizon, too long a stay, a room nobody can see.
        today = india_date(NOW)
        seen["past"] = (
            await _anyone(app, body | {"moveIn": (today - timedelta(days=1)).isoformat()})
        ).json()
        seen["far"] = (
            await _anyone(app, body | {"moveIn": (today + timedelta(days=121)).isoformat()})
        ).json()
        seen["long"] = (await _anyone(app, body | {"stayMonths": 37})).status_code
        seen["no such room"] = (
            await _anyone(app, body | {"roomCategory": str(uuid.uuid7())})
        ).status_code
        hidden = await ops.ok(
            "POST",
            "/v1/ops/properties",
            json={
                "owner": (await ops.owner())["id"],
                "locality": "kamla-nagar",
                "name": f"Unpublished PG {_token()}",
                "addressLine": "House 2, a fictional lane",
                "location": spot(600),
                "locationPrecision": "exact",
                "genderPolicy": "girls",
                "meals": "two",
            },
        )
        built = await ops.ok(
            "POST",
            f"/v1/ops/properties/{hidden['id']}/room-categories",
            json={k: v for k, v in _category("double", 9_000, beds=1).items() if k != "beds"},
        )
        seen["unpublished"] = (
            await _anyone(app, body | {"roomCategory": built["categories"][0]["id"]})
        ).status_code

        # After 30 minutes a quote says so, and a booking can't take it.
        app.state.clock.set(NOW + timedelta(minutes=31))
        seen["expired"] = await ops.ok("GET", f"{QUOTES}/{seen['quote']['id']}")
        async with app.state.sessionmaker() as db, db.begin():
            try:
                await QuoteLookup(db, app.state.clock).usable(uuid.UUID(seen["quote"]["id"]))
            except QuoteExpiredError as error:
                seen["usable"] = error.code
        return seen

    seen = run(scenario)

    assert seen["status"] == 201
    shown = seen["quote"]
    # The engine's numbers, for the same inputs rebuilt from the database, and its digest.
    result, digest, row = seen["engine"]
    assert (shown["monthlyRentPaise"], shown["tokenPaise"], shown["dueAtMoveInPaise"]) == (
        result.monthly_rent_paise,
        result.token_paise,
        result.due_at_move_in_paise,
    )
    assert (row.fee_paise, row.gst_paise, row.owner_fee_total_paise) == (
        result.fee_paise,
        result.gst_paise,
        result.owner_fee_total_paise,
    )
    assert row.inputs_sha256 == digest
    assert shown["monthlyRentPaise"] == 1_100_000
    assert shown["explanation"] == (
        f"Base ₹10,000 · Peak season +15% · Early-bird {MINUS}5% = ₹11,000/month, fixed for"
        " your stay"
    )
    assert [(item["label"], item["bps"]) for item in shown["adjustments"]] == [
        ("Peak season", 1500),
        ("Early-bird", -500),
    ]
    assert (shown["tokenPaise"], shown["dueAtMoveInPaise"], shown["depositPaise"]) == (
        200_000,
        900_000,
        1_000_000,
    )
    assert shown["place"]["roomCategoryLabel"] == "Double sharing"
    # Students pay no fee: the owner's isn't in what they see.
    assert "feePaise" not in shown
    assert seen["asked by"] == seen["student"]
    # The quote stands as it was; a new one has the new rule.
    assert seen["again"] == shown
    assert seen["new"]["monthlyRentPaise"] == 1_070_000
    assert seen["database"] == "a quote never changes once made"
    assert seen["past"]["detail"] == "the move-in date has passed"
    assert seen["far"]["detail"] == "a move-in can be booked at most 120 days ahead"
    assert (seen["long"], seen["no such room"], seen["unpublished"]) == (422, 404, 404)
    assert seen["expired"]["expired"] is True
    assert seen["usable"] == "QUOTE_EXPIRED"


def test_quotes_are_rate_limited_per_address(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[int]:
        listing = await _publish(
            ops,
            name=f"Busy PG {_token()}",
            at=spot(450),
            categories=[_category("single", 12_000, beds=1)],
        )
        body = {
            "roomCategory": listing["categories"][0]["id"],
            "moveIn": MOVE_IN.isoformat(),
            "stayMonths": 6,
        }
        return [(await _anyone(ops.app, body, ip="203.0.113.21")).status_code for _ in range(31)]

    statuses = run(scenario)

    assert statuses == [201] * 30 + [429]


def test_the_calendar_says_what_a_quote_would_week_by_week(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        app = ops.app
        listing = await _publish(
            ops,
            name=f"Calendar PG {_token()}",
            at=spot(420),
            categories=[_category("double", 10_000, beds=2), _category("single", 15_000, beds=1)],
        )
        # Peak season from 1 August: the price changes partway through the twelve weeks.
        await _rules(
            ops,
            listing,
            {
                "label": "Peak season",
                "params": {"kind": "season", "start": "08-01", "end": "08-31", "bps": 1500},
            },
        )
        path = f"/v1/properties/{listing['slug']}/price-calendar"
        seen: dict[str, Any] = {"calendar": await ops.ok("GET", path)}
        seen["cache"] = (await ops.call("GET", path)).headers.get("cache-control")
        double = next(
            room for room in seen["calendar"]["rooms"] if room["label"] == "Double sharing"
        )
        seen["quotes"] = [
            (
                await _anyone(
                    app,
                    {
                        "roomCategory": double["roomCategory"],
                        "moveIn": week["moveIn"],
                        "stayMonths": 11,
                    },
                    ip="203.0.113.22",
                )
            ).json()["monthlyRentPaise"]
            for week in double["weeks"]
        ]
        seen["later"] = await ops.ok("GET", path, params={"from": "2027-10-25", "weeks": 12})
        return seen

    seen = run(scenario)

    calendar = seen["calendar"]
    assert calendar["stayMonths"] == 11
    assert seen["cache"] == "public, max-age=300"
    double = next(room for room in calendar["rooms"] if room["label"] == "Double sharing")
    single = next(room for room in calendar["rooms"] if room["label"] == "Single sharing")
    # Weekly from today, 14 July 2027 in India.
    assert [week["moveIn"] for week in double["weeks"]][:3] == [
        "2027-07-14",
        "2027-07-21",
        "2027-07-28",
    ]
    assert len(double["weeks"]) == 12
    # Each week's rent is what a quote for that move-in says: ₹10,000, then ₹11,500 in August.
    assert [week["monthlyRentPaise"] for week in double["weeks"]] == seen["quotes"]
    assert {week["monthlyRentPaise"] for week in double["weeks"]} == {1_000_000, 1_150_000}
    # Free beds from real inventory.
    assert (double["bedsFree"], single["bedsFree"]) == (2, 1)
    # Never past the booking horizon: 120 days from 14 July is 11 November.
    assert [week["moveIn"] for week in seen["later"]["rooms"][0]["weeks"]] == [
        "2027-10-25",
        "2027-11-01",
        "2027-11-08",
    ]
