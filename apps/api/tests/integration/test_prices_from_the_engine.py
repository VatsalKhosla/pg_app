"""Price summaries from the engine (step 4.7, ADR 0042): a month's range on the map and in search is
what quotes say for that month's move-ins, so the map, a search by budget and the PG page agree;
and a rule set going into force, a band or the caps changing reprice what they move.

Each test's listings are in a locality of its own, as tests run in any order and share one
database."""

import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.actor import Actor, Role
from app.core.money import BasisPoints, Paise
from app.core.outbox import JobContext, OutboxJob
from app.modules.catalog.models import Property
from app.modules.catalog.repository import CatalogRepository
from app.modules.pricing.domain.policies import PricingCaps
from app.modules.pricing.occupancy import NoBookingsYet
from app.modules.pricing.service import CAPS_CHANGED, RULES_CHANGED, PolicyService
from app.modules.search.jobs import REFRESH, caps_changed_handler
from app.modules.search.repository import SummaryRepository
from tests.integration.test_pricing_quotes import _rules
from tests.integration.test_search import _category, _publish
from tests.jobs import RecordedWebCache, run_due_jobs
from tests.staff_api import NOW, Staff, run_as_staff, sign_in, spot

pytestmark = pytest.mark.integration

JULY = {
    "label": "July peak",
    "params": {"kind": "season", "start": "07-01", "end": "07-31", "bps": 1500},
}
EARLY = {"label": "Early-bird", "params": {"kind": "early_bird", "minDaysBefore": 30, "bps": -500}}


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


async def _months(ops: Staff, slug: str) -> dict[date, tuple[int, int]]:
    """The listing's one room's rent range for each month, as search keeps it."""
    async with ops.app.state.sessionmaker() as db, db.begin():
        found = await CatalogRepository(db).property_by_slug(slug)
        assert found is not None
        rows = await SummaryRepository(db).of_property(found.id)
        return {row.month: (row.min_rent_paise, row.max_rent_paise) for row in rows}


def _box(at: dict[str, float], *, margin: float = 0.02) -> str:
    """A map area around a point, as west, south, east, north."""
    west, south = at["lng"] - margin, at["lat"] - margin
    return f"{west:.4f},{south:.4f},{west + 2 * margin:.4f},{south + 2 * margin:.4f}"


def test_the_map_search_and_the_pg_page_agree_month_by_month(run: Callable[..., Any]) -> None:
    """BUILD_PLAN 4.7's done-when, with 4.6's July peak and early-bird."""

    async def scenario(ops: Staff) -> dict[str, Any]:
        token = f"eng{secrets.token_hex(4)}"
        at = spot(510)
        listing = await _publish(
            ops,
            name=f"Engine PG {token}",
            at=at,
            locality="anand-niketan",
            categories=[_category("double", 10_000, beds=2)],
        )
        await run_due_jobs(ops.app)
        seen: dict[str, Any] = {"before": await _months(ops, listing["slug"])}
        await _rules(ops, listing, JULY, EARLY)
        async with ops.app.state.sessionmaker() as db, db.begin():
            seen["queued"] = await db.scalar(
                select(func.count()).where(
                    OutboxJob.kind == RULES_CHANGED, OutboxJob.status == "pending"
                )
            )
        web = RecordedWebCache()
        await run_due_jobs(ops.app, web_cache=web)
        seen["after"] = await _months(ops, listing["slug"])
        seen["revalidated"] = web.tags
        searches = {
            "july, up to ₹11,500": {"move_in_month": "2027-07", "budget_max_paise": 1_150_000},
            "july, up to ₹11,499": {"move_in_month": "2027-07", "budget_max_paise": 1_149_900},
            "august, up to ₹9,500": {"move_in_month": "2027-08", "budget_max_paise": 950_000},
            "august, up to ₹9,499": {"move_in_month": "2027-08", "budget_max_paise": 949_900},
            "august, from ₹10,000": {"move_in_month": "2027-08", "budget_min_paise": 1_000_000},
            "august, from ₹10,001": {"move_in_month": "2027-08", "budget_min_paise": 1_000_100},
        }
        seen["search"] = {}
        for name, params in searches.items():
            page = await ops.ok("GET", "/v1/search/properties", params={"q": token, **params})
            seen["search"][name] = [
                (item["minRentPaise"], item["maxRentPaise"]) for item in page["items"]
            ]
        seen["pins"] = {}
        for month in ("2027-07", "2027-08"):
            pins = await ops.ok(
                "GET",
                "/v1/map/pins",
                params={"bbox": _box(at), "zoom": 13, "q": token, "move_in_month": month},
            )
            seen["pins"][month] = [
                (pin["minRentPaise"], pin["maxRentPaise"]) for pin in pins["pins"]
            ]
        seen["calendar"] = await ops.ok("GET", f"/v1/properties/{listing['slug']}/price-calendar")
        seen["slug"] = listing["slug"]
        return seen

    seen = run(scenario)

    july, august, september = date(2027, 7, 1), date(2027, 8, 1), date(2027, 9, 1)
    # Before any rule, every month is the listed rent.
    assert set(seen["before"].values()) == {(1_000_000, 1_000_000)}
    assert seen["queued"] >= 1
    # From 14 July: the peak for the rest of July; in August the listed rent until the 12th, then
    # the early-bird from 30 days ahead; the early-bird every day after.
    months = seen["after"]
    assert months[july] == (1_150_000, 1_150_000)
    assert months[august] == (950_000, 1_000_000)
    assert months[september] == (950_000, 950_000)
    assert len(months) == 7
    # The PG's pages are told, so its page shows the new prices at once.
    assert [f"listing:{seen['slug']}", "listings"] in seen["revalidated"]
    # Search by budget and the map read the same ranges.
    search = seen["search"]
    assert search["july, up to ₹11,500"] == [(1_150_000, 1_150_000)]
    assert search["july, up to ₹11,499"] == []
    assert search["august, up to ₹9,500"] == [(950_000, 1_000_000)]
    assert search["august, up to ₹9,499"] == []
    assert search["august, from ₹10,000"] == [(950_000, 1_000_000)]
    assert search["august, from ₹10,001"] == []
    assert seen["pins"] == {"2027-07": [(1_150_000, 1_150_000)], "2027-08": [(950_000, 1_000_000)]}
    # And the PG page's weeks sit in their month's range, both ends of August's among them.
    weeks = [
        (date.fromisoformat(week["moveIn"]), week["monthlyRentPaise"])
        for week in seen["calendar"]["rooms"][0]["weeks"]
    ]
    for move_in, rent in weeks:
        low, high = months[move_in.replace(day=1)]
        assert low <= rent <= high
    assert {rent for move_in, rent in weeks if move_in.month == 8} == {950_000, 1_000_000}


def test_a_band_reprices_its_localitys_listings_when_it_starts_and_ends(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _publish(
            ops,
            name=f"Banded PG {secrets.token_hex(4)}",
            at=spot(520),
            locality="dhaula-kuan",
            categories=[_category("double", 10_000, beds=2)],
        )
        await _rules(ops, listing, JULY)
        await run_due_jobs(ops.app)
        seen: dict[str, Any] = {"no band": await _months(ops, listing["slug"])}
        admin = await sign_in(ops.app, ops.client, Role.ADMIN)
        band = await admin.ok(
            "POST",
            "/v1/admin/rent-bands",
            json={
                "locality": "dhaula-kuan",
                "occupancy": "double",
                "minRentPaise": 700_000,
                "maxRentPaise": 1_100_000,
                "source": "internal",
            },
        )
        web = RecordedWebCache()
        await run_due_jobs(ops.app, web_cache=web)
        seen["band"] = await _months(ops, listing["slug"])
        seen["revalidated"] = web.tags
        ops.app.state.clock.set(NOW + timedelta(minutes=1))
        await admin.ok("POST", f"/v1/admin/rent-bands/{band['id']}/end", json={})
        await run_due_jobs(ops.app)
        seen["ended"] = await _months(ops, listing["slug"])
        seen["slug"] = listing["slug"]
        return seen

    seen = run(scenario)

    july = date(2027, 7, 1)
    assert seen["no band"][july] == (1_150_000, 1_150_000)
    # The band's ₹11,000 holds July's peak back, the other months are inside it already.
    assert seen["band"][july] == (1_100_000, 1_100_000)
    assert seen["band"][date(2027, 8, 1)] == (1_000_000, 1_000_000)
    assert [f"listing:{seen['slug']}", "listings"] in seen["revalidated"]
    assert seen["ended"][july] == (1_150_000, 1_150_000)


def test_a_caps_change_reprices_every_listing_once(run: Callable[..., Any]) -> None:
    """In one transaction that's rolled back (the service's own is a savepoint inside it), so
    neither the caps nor a refresh for every listing reaches the shared database."""

    async def scenario(ops: Staff) -> dict[str, Any]:
        app = ops.app
        admin = await sign_in(app, ops.client, Role.ADMIN)
        actor = Actor(
            user_id=admin.user_id,
            user_public_id=uuid.uuid7(),
            roles=frozenset({Role.ADMIN}),
            session_id=0,
            session_public_id=uuid.uuid7(),
        )
        caps = PricingCaps(BasisPoints(3_500), BasisPoints(3_000), Paise(5_000))
        seen: dict[str, Any] = {"refreshes": []}
        async with app.state.engine.connect() as connection:
            outer = await connection.begin()
            db = AsyncSession(
                bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            try:
                changed = await PolicyService(db, app.state.clock).change_caps(actor, caps, note="")
                version = str(changed.version.public_id)
                job = await db.scalar(
                    select(OutboxJob)
                    .where(OutboxJob.kind == CAPS_CHANGED)
                    .where(OutboxJob.dedupe_key == f"{CAPS_CHANGED}:{version}")
                )
                assert job is not None
                seen["payload"] = job.payload
                handler = caps_changed_handler(NoBookingsYet())
                context = JobContext(session=db, clock=app.state.clock, job_id=job.id, attempt=1)
                mine = OutboxJob.dedupe_key.like(f"{REFRESH}:%:caps:{version}")
                counted = select(func.count()).where(OutboxJob.kind == REFRESH, mine)
                for _ in range(2):
                    await handler(context, job.payload)
                    seen["refreshes"].append(await db.scalar(counted))
                seen["listings"] = await db.scalar(select(func.count()).select_from(Property))
                seen["version"] = version
            finally:
                await db.close()
                await outer.rollback()
        return seen

    seen = run(scenario)

    assert seen["payload"] == {"version": seen["version"]}
    # One refresh for each listing, and a second run for the same version adds none.
    assert seen["refreshes"] == [seen["listings"], seen["listings"]]
