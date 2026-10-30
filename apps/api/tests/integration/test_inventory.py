"""Inventory in the API and the database (step 5.1, ADR 0044): two active allocations of one bed
never share a day, however many ask at once; ops place and end blocks; availability is the
domain's own count of what the allocations leave; and offline tenants fill rooms for pricing
while free beds follow on the PG page and in search."""

import asyncio
import random
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.audit import AuditLog
from app.core.outbox import OutboxJob
from app.modules.catalog.models import Bed, Property
from app.modules.inventory.domain.allocations import AllocationKind, Period, free_beds
from app.modules.inventory.models import InventoryAllocation
from app.modules.inventory.repository import to_range
from app.modules.inventory.service import ALLOCATIONS_CHANGED, AvailabilityLookup
from app.modules.search.repository import SummaryRepository
from tests.integration.test_pricing_quotes import _anyone, _rules
from tests.integration.test_search import _category, _publish, _token
from tests.jobs import run_due_jobs
from tests.staff_api import Staff, run_as_staff, spot

pytestmark = pytest.mark.integration

BLOCKS = "/v1/ops/beds/{bed}/blocks"
AUG_1, SEP_1 = date(2027, 8, 1), date(2027, 9, 1)


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


def _beds(listing: dict[str, Any], category: int = 0) -> list[str]:
    """A listing's beds in its room type, by public id."""
    return [bed["id"] for room in listing["categories"][category]["rooms"] for bed in room["beds"]]


async def _internal(ops: Staff, public_ids: list[str]) -> list[int]:
    async with ops.app.state.sessionmaker() as db, db.begin():
        rows = await db.execute(
            select(Bed.public_id, Bed.id).where(Bed.public_id.in_(map(uuid.UUID, public_ids)))
        )
        found = {str(public): internal for public, internal in rows}
    return [found[public] for public in public_ids]


async def _block(ops: Staff, bed: str, kind: str, start: date, end: date | None = None) -> Any:
    body = {
        "kind": kind,
        "start": start.isoformat(),
        "end": None if end is None else end.isoformat(),
    }
    return await ops.call("POST", BLOCKS.format(bed=bed), json=body)


async def _listing(ops: Staff, occupancy: str, beds: int, *, locality: str) -> dict[str, Any]:
    return await _publish(
        ops,
        name=f"Inventory PG {_token()}",
        at=spot(600),
        locality=locality,
        categories=[_category(occupancy, 10_000, beds=beds)],
    )


def test_two_active_allocations_of_a_bed_never_share_a_day(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, bool]:
        listing = await _listing(ops, "double", 2, locality="satya-niketan")
        [bed, _] = await _internal(ops, _beds(listing))
        tries = {
            "august": (Period(AUG_1, SEP_1), AllocationKind.MAINTENANCE, True),
            "overlapping mid-august": (
                Period(date(2027, 8, 15), date(2027, 9, 15)),
                AllocationKind.OFFLINE_TENANT,
                True,
            ),
            "september, from the day august frees it": (
                Period(SEP_1, date(2027, 10, 1)),
                AllocationKind.MAINTENANCE,
                True,
            ),
            "inactive, overlapping": (Period(date(2027, 8, 15)), AllocationKind.MAINTENANCE, False),
            "from november on": (Period(date(2027, 11, 1)), AllocationKind.OFFLINE_TENANT, True),
            "inside the open end": (
                Period(date(2028, 1, 1), date(2028, 1, 5)),
                AllocationKind.MAINTENANCE,
                True,
            ),
        }
        stored = {}
        for name, (period, kind, active) in tries.items():
            try:
                async with ops.app.state.sessionmaker() as db, db.begin():
                    db.add(
                        InventoryAllocation(
                            bed_id=bed, period=to_range(period), kind=kind, is_active=active
                        )
                    )
                stored[name] = True
            except IntegrityError:
                stored[name] = False
        try:
            async with ops.app.state.sessionmaker() as db, db.begin():
                db.add(
                    InventoryAllocation(
                        bed_id=bed,
                        period=to_range(Period(date(2029, 1, 1), date(2029, 2, 1))),
                        kind=AllocationKind.BOOKING,
                    )
                )
            stored["a booking without its booking"] = True
        except IntegrityError:
            stored["a booking without its booking"] = False
        return stored

    stored = run(scenario)

    assert stored == {
        "august": True,
        "overlapping mid-august": False,
        "september, from the day august frees it": True,
        "inactive, overlapping": True,
        "from november on": True,
        "inside the open end": False,
        "a booking without its booking": False,
    }


def test_thirty_ops_asking_at_once_hold_a_bed_once(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> tuple[list[int], int]:
        listing = await _listing(ops, "single", 1, locality="satya-niketan")
        [bed] = _beds(listing)
        answers = await asyncio.gather(
            *(
                _block(ops, bed, "offline_tenant", AUG_1 + timedelta(days=day % 5))
                for day in range(30)
            )
        )
        [internal] = await _internal(ops, [bed])
        async with ops.app.state.sessionmaker() as db, db.begin():
            active = await db.scalar(
                select(func.count()).where(
                    InventoryAllocation.bed_id == internal, InventoryAllocation.is_active
                )
            )
        return sorted(answer.status_code for answer in answers), active or 0

    statuses, active = run(scenario)

    assert statuses == [201] + [409] * 29
    assert active == 1


def test_ops_place_end_and_cancel_blocks(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, "quad", 4, locality="satya-niketan")
        beds = _beds(listing)
        window = f"/v1/ops/properties/{listing['id']}/inventory"
        query = {"from": AUG_1.isoformat(), "days": 30}
        seen: dict[str, Any] = {"before": await ops.ok("GET", window, params=query)}
        repair = await _block(ops, beds[0], "maintenance", date(2027, 8, 5), date(2027, 8, 10))
        seen["repair"] = repair.json()
        seen["clash"] = (await _block(ops, beds[0], "offline_tenant", date(2027, 8, 8))).json()
        tenant = (await _block(ops, beds[1], "offline_tenant", AUG_1)).json()
        seen["during"] = await ops.ok("GET", window, params=query)
        end = "/v1/ops/blocks/{block}/end"
        seen["moved out"] = await ops.ok(
            "POST", end.format(block=tenant["id"]), json={"on": SEP_1.isoformat()}
        )
        seen["later"] = (
            await _block(ops, beds[1], "maintenance", date(2027, 9, 10), date(2027, 9, 20))
        ).json()
        seen["too long"] = (
            await ops.call("POST", end.format(block=tenant["id"]), json={"on": "2027-09-15"})
        ).json()
        seen["cancelled"] = await ops.ok(
            "POST", end.format(block=seen["repair"]["id"]), json={"on": "2027-08-05"}
        )
        seen["again"] = (
            await ops.call(
                "POST", end.format(block=seen["repair"]["id"]), json={"on": "2027-08-06"}
            )
        ).json()
        seen["backwards"] = (
            await _block(ops, beds[2], "maintenance", date(2027, 8, 10), date(2027, 8, 9))
        ).json()
        seen["after"] = await ops.ok("GET", window, params=query)
        async with ops.app.state.sessionmaker() as db, db.begin():
            seen["audit"] = list(
                await db.scalars(
                    select(AuditLog.action)
                    .where(AuditLog.entity_id.in_([tenant["id"], seen["repair"]["id"]]))
                    .order_by(AuditLog.id)
                )
            )
            seen["queued"] = await db.scalar(
                select(func.count()).where(OutboxJob.kind == ALLOCATIONS_CHANGED)
            )
        return seen

    seen = run(scenario)

    room = seen["before"]["categories"][0]
    assert (room["activeBeds"], room["freeBeds"]) == (4, 4)
    assert (seen["repair"]["kind"], seen["repair"]["start"], seen["repair"]["end"]) == (
        "maintenance",
        "2027-08-05",
        "2027-08-10",
    )
    assert seen["clash"]["code"] == "BED_UNAVAILABLE"
    assert seen["clash"]["detail"].endswith(
        "is held by maintenance from 5 Aug 2027 until 10 Aug 2027."
    )
    during = seen["during"]["categories"][0]
    assert during["freeBeds"] == 2
    held = {bed["label"]: [item["kind"] for item in bed["allocations"]] for bed in during["beds"]}
    assert sorted(held.values()) == [[], [], ["maintenance"], ["offline_tenant"]]
    assert (seen["moved out"]["end"], seen["moved out"]["active"]) == ("2027-09-01", True)
    # A later end would run into September's maintenance.
    assert seen["too long"]["code"] == "BED_UNAVAILABLE"
    assert (seen["cancelled"]["active"], seen["again"]["code"]) == (False, "INVALID_TRANSITION")
    assert seen["backwards"]["code"] == "BLOCK_INVALID"
    assert seen["after"]["categories"][0]["freeBeds"] == 3
    assert seen["audit"] == [
        "inventory.block_placed",
        "inventory.block_placed",
        "inventory.block_ended",
        "inventory.block_cancelled",
    ]
    assert seen["queued"] >= 4


def test_availability_is_the_domains_count_of_what_allocations_leave(
    run: Callable[..., Any],
) -> None:
    """Random allocations on four beds, each scenario rolled back: the database's free beds are
    exactly the domain's plain definition, for random stays."""

    async def scenario(ops: Staff) -> list[tuple[int, int]]:
        listing = await _listing(ops, "quad", 4, locality="satya-niketan")
        beds = await _internal(ops, _beds(listing))
        async with ops.app.state.sessionmaker() as db, db.begin():
            property_id = await db.scalar(
                select(Property.id).where(Property.public_id == uuid.UUID(listing["id"]))
            )
        assert property_id is not None
        dice = random.Random(5_100)  # noqa: S311 - reproducible scenarios, not secrets
        compared = []
        async with ops.app.state.engine.connect() as connection:
            outer = await connection.begin()
            db = AsyncSession(
                bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            try:
                for _ in range(40):
                    async with db.begin_nested() as each:
                        held: list[tuple[int, Period]] = []
                        for bed in beds:
                            day = AUG_1 + timedelta(days=dice.randrange(0, 20))
                            for _ in range(dice.randrange(0, 4)):
                                length = dice.choice([None, 3, 10, 30])
                                period = Period(
                                    day, None if length is None else day + timedelta(days=length)
                                )
                                db.add(
                                    InventoryAllocation(
                                        bed_id=bed,
                                        period=to_range(period),
                                        kind=AllocationKind.MAINTENANCE,
                                    )
                                )
                                held.append((bed, period))
                                if period.end is None:
                                    break
                                day = period.end + timedelta(days=dice.randrange(0, 5))
                        await db.flush()
                        start = AUG_1 + timedelta(days=dice.randrange(0, 60))
                        wanted = Period(start, start + timedelta(days=dice.choice([1, 7, 30, 330])))
                        found = await AvailabilityLookup(db).free_beds(property_id, wanted)
                        expected = len(free_beds(set(beds), held, wanted))
                        compared.append((sum(found.values()), expected))
                        await each.rollback()
            finally:
                await db.close()
                await outer.rollback()
        return compared

    compared = run(scenario)

    assert len(compared) == 40
    assert all(found == expected for found, expected in compared), compared
    # The scenarios cover full, partly free and empty rooms alike.
    assert {expected for _, expected in compared} >= {0, 4}


def test_offline_tenants_fill_rooms_for_pricing_and_free_beds_follow(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        app = ops.app
        listing = await _listing(ops, "double", 2, locality="satya-niketan")
        room = listing["categories"][0]["id"]
        await _rules(
            ops,
            listing,
            {
                "label": "Filling up",
                "params": {"kind": "occupancy", "tiers": [{"minOccupancyBps": 5000, "bps": 1000}]},
            },
        )
        body = {"roomCategory": room, "moveIn": "2027-08-20", "stayMonths": 11}
        seen: dict[str, Any] = {"empty": (await _anyone(app, body, ip="203.0.113.50")).json()}
        first, second = _beds(listing)
        assert (await _block(ops, first, "offline_tenant", AUG_1)).status_code == 201
        assert (
            await _block(ops, second, "maintenance", date(2027, 8, 5), date(2027, 8, 10))
        ).status_code == 201
        seen["half full"] = (await _anyone(app, body, ip="203.0.113.50")).json()
        seen["calendar"] = await ops.ok("GET", f"/v1/properties/{listing['slug']}/price-calendar")
        await run_due_jobs(app)
        async with app.state.sessionmaker() as db, db.begin():
            property_id = await db.scalar(
                select(Property.id).where(Property.public_id == uuid.UUID(listing["id"]))
            )
            assert property_id is not None
            rows = await SummaryRepository(db).of_property(property_id)
            seen["summaries"] = {row.month: row.available_beds for row in rows}
        return seen

    seen = run(scenario)

    # One of two beds taken by a tenant from 1 August: 50%, so the occupancy tier's +10% applies;
    # maintenance holds a bed but fills no room.
    assert seen["empty"]["monthlyRentPaise"] == 1_000_000
    assert seen["half full"]["monthlyRentPaise"] == 1_100_000
    assert [item["label"] for item in seen["half full"]["adjustments"]] == ["Filling up"]
    # Neither bed is free for an eleven-month stay from this week.
    assert seen["calendar"]["rooms"][0]["bedsFree"] == 0
    summaries = seen["summaries"]
    # July's and August's stays meet the maintenance; from September only the tenant's bed is
    # held.
    assert summaries[date(2027, 7, 1)] == 0
    assert summaries[date(2027, 8, 1)] == 0
    assert summaries[date(2027, 9, 1)] == 1
