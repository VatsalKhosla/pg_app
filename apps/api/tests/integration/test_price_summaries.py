"""Price summaries (step 3.1, ADR 0027): worked out from base rents, refreshed through the outbox
after every catalog change to rents, rooms or beds, and every night for every listing."""

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.outbox import OutboxJob, OutboxWorker
from app.jobs import build_registry
from app.modules.catalog.repository import CatalogRepository
from app.modules.search.repository import SummaryRepository
from app.modules.search.service import RECOMPUTE, PriceSummaries
from tests.staff_api import NOW, Staff, run_as_staff, spot
from tests.storage import BUCKETS, MemoryStorage

pytestmark = pytest.mark.integration

Ops = Staff


@pytest.fixture
def run(make_settings: Callable[..., Settings], database_url: str) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Ops], Awaitable[Any]]) -> Any:
        return run_as_staff(make_settings(database_url=database_url), scenario)

    return run_scenario


async def _run_worker(ops: Ops) -> None:
    """Every job that's due, as the worker process runs them."""
    worker = OutboxWorker(
        sessionmaker=ops.app.state.sessionmaker,
        registry=build_registry(storage=MemoryStorage(), buckets=BUCKETS),
        clock=ops.app.state.clock,
        worker_id="test",
        batch_size=50,
    )
    while await worker.run_once():
        pass


async def _listing(ops: Ops, *, at: dict[str, float]) -> dict[str, Any]:
    """A listing with a double room category and room 101's two beds."""
    listing = await ops.listing(await ops.owner(), at=at)
    built = await ops.ok(
        "POST",
        f"/v1/ops/properties/{listing['id']}/room-categories",
        json={
            "occupancy": "double",
            "label": "Double sharing",
            "baseRentPaise": 1_200_000,
            "securityDepositPaise": 1_200_000,
        },
    )
    return await ops.ok(
        "POST",
        f"/v1/ops/room-categories/{built['categories'][0]['id']}/rooms",
        json={"label": "101", "beds": 2},
    )


async def _property_id(ops: Ops, listing: dict[str, Any]) -> int:
    async with ops.app.state.sessionmaker() as db, db.begin():
        found = await CatalogRepository(db).property_by_slug(listing["slug"])
        assert found is not None
        return found.id


async def _summaries(ops: Ops, property_id: int) -> list[tuple[date, int, int, int]]:
    async with ops.app.state.sessionmaker() as db, db.begin():
        rows = await SummaryRepository(db).of_property(property_id)
        return [
            (row.month, row.min_rent_paise, row.max_rent_paise, row.available_beds) for row in rows
        ]


async def _pending(ops: Ops, property_id: int) -> list[datetime]:
    """When the pending jobs about this listing's inventory are due."""
    async with ops.app.state.sessionmaker() as db, db.begin():
        rows = await db.scalars(
            select(OutboxJob.run_at).where(
                OutboxJob.kind == "catalog.inventory_changed",
                OutboxJob.status == "pending",
                OutboxJob.payload["property_id"].as_integer() == property_id,
            )
        )
        return list(rows)


def test_a_listings_summaries_follow_a_rent_change_within_seconds(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        built = await _listing(ops, at=spot(2_300, bearing=80))
        property_id = await _property_id(ops, built)
        await _run_worker(ops)
        before = await _summaries(ops, property_id)
        category = built["categories"][0]["id"]
        await ops.ok(
            "PATCH", f"/v1/ops/room-categories/{category}", json={"baseRentPaise": 1_350_000}
        )
        due = await _pending(ops, property_id)
        await _run_worker(ops)
        async with ops.app.state.sessionmaker() as db, db.begin():
            computed = [
                row.computed_at for row in await SummaryRepository(db).of_property(property_id)
            ]
        return {
            "before": before,
            "due": due,
            "after": await _summaries(ops, property_id),
            "computed": computed,
        }

    found = run(scenario)

    # This month and the next six, at the base rent, with both beds free.
    assert [row[0] for row in found["before"]] == [
        date(2027, 7, 1),
        date(2027, 8, 1),
        date(2027, 9, 1),
        date(2027, 10, 1),
        date(2027, 11, 1),
        date(2027, 12, 1),
        date(2028, 1, 1),
    ]
    assert {row[1:] for row in found["before"]} == {(1_200_000, 1_200_000, 2)}
    # The change queued a refresh due at once, which the worker (polling every second) ran.
    assert found["due"]
    assert all(due <= NOW + timedelta(minutes=1) for due in found["due"])
    assert {row[1:] for row in found["after"]} == {(1_350_000, 1_350_000, 2)}
    assert set(found["computed"]) == {NOW}


def test_only_categories_with_a_bed_to_sell_are_summarised(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        built = await _listing(ops, at=spot(2_500, bearing=170))
        property_id = await _property_id(ops, built)
        path = f"/v1/ops/properties/{built['id']}"
        # A second category with no rooms yet: nothing to sell, so nothing to summarise.
        await ops.ok(
            "POST",
            f"{path}/room-categories",
            json={
                "occupancy": "single",
                "label": "Single",
                "baseRentPaise": 1_800_000,
                "securityDepositPaise": 1_800_000,
            },
        )
        bed = built["categories"][0]["rooms"][0]["beds"][0]["id"]
        await ops.ok("PATCH", f"/v1/ops/beds/{bed}", json={"status": "inactive"})
        await _run_worker(ops)
        one_bed = await _summaries(ops, property_id)
        await ops.ok(
            "PATCH",
            f"/v1/ops/room-categories/{built['categories'][0]['id']}",
            json={"status": "inactive"},
        )
        await _run_worker(ops)
        return {"one bed": one_bed, "none": await _summaries(ops, property_id)}

    found = run(scenario)

    assert {row[1:] for row in found["one bed"]} == {(1_200_000, 1_200_000, 1)}
    assert found["none"] == []


def test_the_nightly_refresh_queues_every_listing_once_a_day_and_rolls_the_months(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        built = await _listing(ops, at=spot(2_700, bearing=260))
        property_id = await _property_id(ops, built)
        # The first night of a new month, in India: 00:30 on 1 August is 19:00 UTC on 31 July.
        ops.app.state.clock.set(datetime(2027, 7, 31, 19, 0, tzinfo=UTC))
        added = []
        for _ in range(2):
            async with ops.app.state.sessionmaker() as db, db.begin():
                added.append(await PriceSummaries(db, ops.app.state.clock).recompute_all())
        async with ops.app.state.sessionmaker() as db, db.begin():
            queued = await db.scalar(
                select(OutboxJob.id).where(
                    OutboxJob.dedupe_key == f"{RECOMPUTE}:{property_id}:2027-08-01"
                )
            )
        await _run_worker(ops)
        return {"added": added, "queued": queued, "months": await _summaries(ops, property_id)}

    found = run(scenario)

    first, second = found["added"]
    assert first >= 1
    assert found["queued"] is not None
    # The same night again adds nothing.
    assert second == 0
    assert [row[0] for row in found["months"]][:2] == [date(2027, 8, 1), date(2027, 9, 1)]
    assert found["months"][-1][0] == date(2028, 2, 1)
