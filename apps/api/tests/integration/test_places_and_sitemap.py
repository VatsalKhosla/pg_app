"""Where the PGs are, the sitemap's list, and telling the web app (step 3.6, ADR 0032).

The campuses and localities with live PGs; every live listing a page at a time with its last
change; and the revalidation each catalog change asks for, which the nightly refresh doesn't.
The database is shared with other tests, so counts are compared before and after, and only this
test's listings are looked for.
"""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.calendar import india_date
from app.core.outbox import enqueue
from app.modules.search.models import SearchListing
from app.modules.search.service import REFRESH
from tests.flags import FixedFlags
from tests.integration.test_search import _category, _publish, _token
from tests.jobs import RecordedWebCache, run_due_jobs
from tests.staff_api import NOW, Staff, run_as_staff, spot

pytestmark = pytest.mark.integration

PLACES = "/v1/search/places"
SITEMAP = "/v1/search/sitemap"


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


def _place(places: dict[str, Any], kind: str, slug: str) -> dict[str, Any] | None:
    return next(
        (item for item in places["items"] if item["kind"] == kind and item["slug"] == slug), None
    )


async def _sitemap(ops: Staff, *, limit: int) -> list[dict[str, Any]]:
    """Every page of the sitemap's list, followed by its cursors."""
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        page = await ops.ok("GET", SITEMAP, params=params)
        items.extend(page["items"])
        cursor = page["nextCursor"]
        if cursor is None:
            return items


def test_places_count_the_verified_live_pgs_near_each_campus_and_in_each_locality(
    run: Callable[..., Any],
) -> None:
    token = _token()

    async def scenario(ops: Staff) -> dict[str, Any]:
        before = await ops.ok("GET", PLACES)
        await _publish(
            ops,
            name=f"Pallavi PG {token}",
            at=spot(600),
            categories=[_category("double", 11_500, beds=2)],
        )
        # Search shows only verified PGs, so places don't count this one, published while
        # verified_only was off.
        ops.app.state.flags = FixedFlags(verified_only=False)
        await _publish(
            ops,
            name=f"Unchecked PG {token}",
            at=spot(700),
            categories=[_category("double", 11_500, beds=2)],
            verified=False,
        )
        ops.app.state.flags = FixedFlags()
        await run_due_jobs(ops.app)
        return {"before": before, "after": await ops.ok("GET", PLACES)}

    found = run(scenario)

    before, after = found["before"], found["after"]
    # Near Hindu College (600 m) and in Kamla Nagar: one more of each.
    for kind, slug in (("campus", "hindu-college"), ("locality", "kamla-nagar")):
        was, now = _place(before, kind, slug), _place(after, kind, slug)
        assert now is not None
        assert now["listings"] == (0 if was is None else was["listings"]) + 1
        assert now["minRentPaise"] <= 1_150_000 <= now["maxRentPaise"]
    assert after["month"] == india_date(NOW).replace(day=1).isoformat()
    assert after["radiusM"] == 3_000
    # Campuses first, then localities; the most PGs first within each; none without any.
    kinds = [item["kind"] for item in after["items"]]
    assert kinds == sorted(kinds)
    for kind in ("campus", "locality"):
        counts = [item["listings"] for item in after["items"] if item["kind"] == kind]
        assert counts == sorted(counts, reverse=True)
    assert all(item["listings"] >= 1 for item in after["items"])


def test_the_sitemap_lists_each_page_the_public_may_see_once_with_its_last_change(
    run: Callable[..., Any],
) -> None:
    token = _token()

    async def scenario(ops: Staff) -> dict[str, Any]:
        shown = await _publish(
            ops,
            name=f"Sitara PG {token}",
            at=spot(800),
            categories=[_category("single", 14_000, beds=1)],
        )
        ops.app.state.flags = FixedFlags(verified_only=False)
        unchecked = await _publish(
            ops,
            name=f"Unvisited PG {token}",
            at=spot(900),
            categories=[_category("single", 14_000, beds=1)],
            verified=False,
        )
        await run_due_jobs(ops.app)
        ops.app.state.flags = FixedFlags(verified_only=True)
        verified_only = await _sitemap(ops, limit=2)
        ops.app.state.flags = FixedFlags(verified_only=False)
        everything = await _sitemap(ops, limit=1_000)
        refused = await ops.call("GET", SITEMAP, params={"cursor": "not-a-cursor"})
        return {
            "shown": shown["slug"],
            "unchecked": unchecked["slug"],
            "verified only": verified_only,
            "everything": everything,
            "refused": (refused.status_code, refused.json()["code"]),
        }

    found = run(scenario)

    # Each listing once, however the pages are cut.
    slugs = [item["slug"] for item in found["verified only"]]
    assert len(slugs) == len(set(slugs))
    # While verified_only is on, an unverified listing's page is hidden, so it isn't listed.
    assert found["shown"] in slugs
    assert found["unchecked"] not in slugs
    assert found["unchecked"] in [item["slug"] for item in found["everything"]]
    shown = next(item for item in found["everything"] if item["slug"] == found["shown"])
    assert shown["changedAt"] == NOW.isoformat().replace("+00:00", "Z")
    assert found["refused"] == (422, "SEARCH_INVALID")


def test_each_catalog_change_revalidates_the_listings_pages_and_the_nightly_refresh_does_not(
    run: Callable[..., Any],
) -> None:
    token = _token()

    async def scenario(ops: Staff) -> dict[str, Any]:
        clock = ops.app.state.clock
        web = RecordedWebCache()
        listing = await _publish(
            ops,
            name=f"Revati PG {token}",
            at=spot(1_000),
            categories=[_category("triple", 8_000, beds=3)],
        )
        slug = listing["slug"]
        await run_due_jobs(ops.app, web_cache=web)
        seen: dict[str, Any] = {
            "published": [tags for tags in web.tags if f"listing:{slug}" in tags]
        }

        async def asked_since(mark: int) -> list[list[str]]:
            await run_due_jobs(ops.app, web_cache=web)
            return [tags for tags in web.tags[mark:] if f"listing:{slug}" in tags]

        async def changed_at() -> str | None:
            entry = next(
                (item for item in await _sitemap(ops, limit=1_000) if item["slug"] == slug), None
            )
            return None if entry is None else entry["changedAt"]

        seen["published at"] = await changed_at()
        # The nightly refresh works the entry out again, but nothing about it changed.
        clock.advance(timedelta(hours=1))
        async with ops.app.state.sessionmaker() as db, db.begin():
            property_id = await db.scalar(
                select(SearchListing.property_id).where(SearchListing.slug == slug)
            )
            await enqueue(db, REFRESH, {"property_id": property_id}, clock=clock)
        mark = len(web.tags)
        seen["nightly"] = await asked_since(mark)
        seen["after nightly"] = await changed_at()
        # An edit ops make.
        clock.advance(timedelta(hours=1))
        mark = len(web.tags)
        await ops.ok(
            "PATCH",
            f"/v1/ops/properties/{listing['id']}",
            json={"description": "A fictional PG, its description edited by a test."},
        )
        seen["edited"] = await asked_since(mark)
        seen["after edit"] = await changed_at()
        # Paused: off the site, so its page must go too.
        mark = len(web.tags)
        await ops.ok(
            "POST", f"/v1/ops/properties/{listing['id']}/status", json={"status": "paused"}
        )
        seen["paused"] = await asked_since(mark)
        seen["after pause"] = await changed_at()
        # A draft the public has never seen asks for nothing.
        owner = await ops.owner()
        mark = len(web.tags)
        await ops.ok(
            "POST",
            "/v1/ops/properties",
            json={
                "owner": owner["id"],
                "locality": "kamla-nagar",
                "name": f"Drafted PG {token}",
                "addressLine": "House 2, a fictional lane",
                "location": spot(1_100),
                "locationPrecision": "exact",
                "genderPolicy": "boys",
                "meals": "none",
            },
        )
        await run_due_jobs(ops.app, web_cache=web)
        seen["draft"] = [tags for tags in web.tags[mark:] if any(token in tag for tag in tags)]
        seen["slug"] = slug
        return seen

    found = run(scenario)

    tags = [f"listing:{found['slug']}", "listings"]
    # Every catalog event about it, from the draft to publishing, finds it public by the time
    # the worker gets to it, so each asks again; harmless, as revalidating is idempotent.
    assert found["published"]
    assert all(asked == tags for asked in found["published"])
    assert found["published at"] == NOW.isoformat().replace("+00:00", "Z")
    assert found["nightly"] == []
    assert found["after nightly"] == found["published at"]
    assert found["edited"] == [tags]
    assert found["after edit"] == (NOW + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    assert found["paused"] == [tags]
    assert found["after pause"] is None
    assert found["draft"] == []
