"""The catalog in PostgreSQL (step 2.2): owners and listings created, updated and published, their
rooms and beds, the database's own checks on money, and the geo queries over display points.
Done when migrations apply cleanly and these cover create, update, publish and geo queries.

Every listing here is fictional, placed by moving away from a seeded campus, so no coordinate is
typed in.
"""

import asyncio
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.actor import Actor, Role
from app.core.audit import AuditLog
from app.core.clock import FrozenClock
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.geometry import Bounds, Point, distance_m
from app.core.money import Paise, rupees
from app.modules.catalog.domain.charges import (
    ChargeKind,
    MeteredCharge,
    MonthlyCharge,
    OneTimeCharge,
)
from app.modules.catalog.domain.listing import (
    GenderPolicy,
    LocationPrecision,
    Meals,
    PropertyStatus,
)
from app.modules.catalog.domain.location import MAX_OFFSET_M, MIN_OFFSET_M, Offset, moved
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.catalog.errors import (
    LabelTakenError,
    ListingIncompleteError,
    ListingInvalidError,
    RoomFullError,
)
from app.modules.catalog.models import Owner, Property, RoomCategory
from app.modules.catalog.repository import CatalogRepository, charges_from_json
from app.modules.catalog.service import (
    CategoryDraft,
    InventoryService,
    ListingService,
    OwnerService,
    PropertyDraft,
)
from app.modules.geo.reference import read_reference_data
from app.modules.geo.service import GeoReferenceLoader
from app.modules.identity.repository import UserRepository
from tests.flags import FixedFlags
from tests.storage import BUCKETS

pytestmark = pytest.mark.integration

STOP_BEDS = text(
    "UPDATE beds SET status = 'inactive' WHERE room_id IN ("
    " SELECT rooms.id FROM rooms"
    " JOIN room_categories ON room_categories.id = rooms.room_category_id"
    " WHERE room_categories.property_id = :id)"
)
STOP_CATEGORIES = text("UPDATE room_categories SET status = 'inactive' WHERE property_id = :id")

DATA = read_reference_data()
CAMPUS = next(campus for campus in DATA.campuses if campus.slug == "hindu-college")
LOCALITY = next(locality for locality in DATA.localities if locality.slug == "kamla-nagar")
NOW = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)

type Sessionmaker = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class World:
    sessions: Sessionmaker
    clock: FrozenClock
    staff: Actor
    owner: Owner

    def listings(self, db: AsyncSession) -> ListingService:
        # These are step 2.2's listings, published without the verification visit that
        # verified_only asks for (tests/integration/test_verification.py covers that).
        return ListingService(
            db, self.clock, buckets=BUCKETS, flags=FixedFlags(verified_only=False)
        )

    def inventory(self, db: AsyncSession) -> InventoryService:
        return InventoryService(db, self.clock)


def _phone() -> str:
    return f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"


def _away(metres: float, *, bearing: float = 90.0) -> Point:
    """A fictional listing's spot: ``metres`` from the campus, east unless told otherwise."""
    return moved(CAMPUS.location.point, Offset(bearing_deg=bearing, distance_m=metres))


def _draft(owner: Owner, name: str, at: Point) -> PropertyDraft:
    return PropertyDraft(
        owner=owner.public_id,
        locality=LOCALITY.slug,
        name=name,
        address_line="House 1, a fictional lane",
        location=at,
        location_precision=LocationPrecision.EXACT,
        gender_policy=GenderPolicy.GIRLS,
        meals=Meals.TWO,
        house_rules=("No smoking",),
    )


DOUBLE = CategoryDraft(
    occupancy=Occupancy.DOUBLE,
    label="Double sharing, AC",
    ac=True,
    attached_bath=True,
    base_rent=rupees(12_000),
    owner_min_rent=rupees(11_000),
    owner_max_rent=rupees(15_000),
    security_deposit=rupees(12_000),
    mandatory_charges=(
        MeteredCharge(
            ChargeKind.ELECTRICITY,
            "Electricity",
            rate=rupees(9),
            unit="kWh",
            monthly_estimate=rupees(800),
        ),
        MonthlyCharge(ChargeKind.MAINTENANCE, "Maintenance", rupees(500)),
        OneTimeCharge(ChargeKind.REGISTRATION, "Registration", rupees(1_000)),
    ),
)


@pytest.fixture
def run(database_url: str) -> Callable[[Callable[[World], Awaitable[Any]]], Any]:
    """Run a scenario with the geo data loaded, a staff member and an owner."""

    def run_scenario(scenario: Callable[[World], Awaitable[Any]]) -> Any:
        async def wrapped() -> Any:
            engine = create_async_engine(database_url, poolclass=NullPool)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            clock = FrozenClock(NOW)
            try:
                async with sessions() as db:
                    await GeoReferenceLoader(db, clock).load(DATA)
                async with sessions() as db, db.begin():
                    users = UserRepository(db)
                    ops = await users.add(phone_e164=_phone(), roles=[Role.OPS])
                staff = Actor(
                    user_id=ops.id,
                    user_public_id=ops.public_id,
                    roles=frozenset({Role.OPS}),
                    session_id=0,
                    session_public_id=uuid.uuid7(),
                )
                async with sessions() as db:
                    record = await OwnerService(db, clock).add(
                        staff,
                        phone=_phone(),
                        legal_name="Fictional Stays Private Limited",
                        business_name="Fictional Stays",
                    )
                owner = record.owner
                return await scenario(World(sessions, clock, staff, owner))
            finally:
                await engine.dispose()

        return asyncio.run(wrapped())

    return run_scenario


async def _create(world: World, name: str, at: Point) -> Property:
    async with world.sessions() as db:
        return await world.listings(db).create_property(world.staff, _draft(world.owner, name, at))


async def _points(world: World, found: Property) -> tuple[Point, Point]:
    async with world.sessions() as db:
        return await CatalogRepository(db).points(found.id)


async def _sellable(world: World, found: Property) -> Property:
    """Give the property a room category with a room and a bed."""
    async with world.sessions() as db:
        category = await world.inventory(db).add_room_category(world.staff, found.public_id, DOUBLE)
    async with world.sessions() as db:
        room = await world.inventory(db).add_room(world.staff, category.public_id, label="101")
    async with world.sessions() as db:
        await world.inventory(db).add_bed(world.staff, room.public_id, label="A")
    return found


async def _move(world: World, found: Property, target: PropertyStatus) -> Property:
    async with world.sessions() as db:
        return await world.listings(db).move(world.staff, found.public_id, target)


def test_a_new_listing_is_a_draft_with_a_slug_and_a_display_point_nearby(
    run: Callable[..., Any],
) -> None:
    name = f"Fictional Residency {secrets.token_hex(3)}"

    async def scenario(world: World) -> tuple[Property, Property, Point, Point, int]:
        first = await _create(world, name, _away(400))
        second = await _create(world, name, _away(450))
        exact, display = await _points(world, first)
        async with world.sessions() as db:
            logged = await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "catalog.property_created")
                .where(AuditLog.entity_id == str(first.public_id))
            )
        return first, second, exact, display, logged or 0

    first, second, exact, display, logged = run(scenario)

    assert first.status == PropertyStatus.DRAFT
    assert first.verification_status == "unverified"
    assert first.slug.endswith("-kamla-nagar")
    assert second.slug == f"{first.slug}-2"
    assert exact == _away(400)
    assert MIN_OFFSET_M - 0.05 <= distance_m(exact, display) <= MAX_OFFSET_M + 0.05
    assert logged == 1


def test_moving_the_pin_moves_the_display_point_and_nothing_else_does(
    run: Callable[..., Any],
) -> None:
    async def scenario(world: World) -> tuple[Point, Point, Point, Point, Point, Point, str]:
        found = await _create(world, "Fictional Lodge", _away(600))
        before = await _points(world, found)
        async with world.sessions() as db:
            renamed = await world.listings(db).update_property(
                world.staff,
                found.public_id,
                {"name": "Fictional Lodge Annexe", "location": before[0]},
            )
        same = await _points(world, found)
        async with world.sessions() as db:
            await world.listings(db).update_property(
                world.staff, found.public_id, {"location": _away(700)}
            )
        after = await _points(world, found)
        return (*before, *same, *after, renamed.name)

    exact, display, same_exact, same_display, new_exact, new_display, name = run(scenario)

    assert name == "Fictional Lodge Annexe"
    assert (same_exact, same_display) == (exact, display)
    assert new_exact == _away(700)
    assert new_display != display
    assert MIN_OFFSET_M - 0.05 <= distance_m(new_exact, new_display) <= MAX_OFFSET_M + 0.05


def test_publishing_needs_a_bed_to_sell_and_keeps_its_first_date(
    run: Callable[..., Any],
) -> None:
    async def scenario(world: World) -> dict[str, Any]:
        found = await _create(world, "Fictional Hostel", _away(800))
        outcome: dict[str, Any] = {}
        try:
            await _move(world, found, PropertyStatus.PUBLISHED)
        except ListingIncompleteError as error:
            outcome["incomplete"] = error.problems
        await _sellable(world, found)
        published = await _move(world, found, PropertyStatus.PUBLISHED)
        outcome["published_at"] = published.published_at
        await _move(world, found, PropertyStatus.PAUSED)
        world.clock.advance(timedelta(days=3))
        again = await _move(world, found, PropertyStatus.PUBLISHED)
        outcome["again_at"] = again.published_at
        try:
            await _move(world, found, PropertyStatus.DRAFT)
        except InvalidTransitionError:
            outcome["published_to_draft"] = "refused"
        await _move(world, found, PropertyStatus.DELISTED)
        outcome["relisted"] = (await _move(world, found, PropertyStatus.DRAFT)).status
        return outcome

    outcome = run(scenario)

    assert outcome["incomplete"]
    assert outcome["published_at"] == NOW
    assert outcome["again_at"] == NOW
    assert outcome["published_to_draft"] == "refused"
    assert outcome["relisted"] == PropertyStatus.DRAFT


def test_an_inactive_category_or_bed_is_nothing_to_sell(run: Callable[..., Any]) -> None:
    async def scenario(world: World) -> tuple[int, int, int]:
        found = await _sellable(world, await _create(world, "Fictional Rooms", _away(850)))
        async with world.sessions() as db:
            sellable = await CatalogRepository(db).sellable_categories(found.id)
            await db.execute(STOP_BEDS, {"id": found.id})
            no_beds = await CatalogRepository(db).sellable_categories(found.id)
            await db.rollback()
        async with world.sessions() as db:
            await db.execute(STOP_CATEGORIES, {"id": found.id})
            no_categories = await CatalogRepository(db).sellable_categories(found.id)
            await db.rollback()
        return sellable, no_beds, no_categories

    assert run(scenario) == (1, 0, 0)


def test_a_room_takes_no_more_beds_than_its_occupancy_and_labels_are_unique(
    run: Callable[..., Any],
) -> None:
    async def scenario(world: World) -> list[str]:
        found = await _create(world, "Fictional Nest", _away(900))
        async with world.sessions() as db:
            category = await world.inventory(db).add_room_category(
                world.staff, found.public_id, DOUBLE
            )
        async with world.sessions() as db:
            room = await world.inventory(db).add_room(
                world.staff, category.public_id, label="201", floor=2
            )
        refused = []
        for label in ("A", "B", "A", "C"):
            try:
                async with world.sessions() as db:
                    await world.inventory(db).add_bed(world.staff, room.public_id, label=label)
            except LabelTakenError:
                refused.append(f"{label}: label taken")
            except RoomFullError:
                refused.append(f"{label}: room full")
        try:
            async with world.sessions() as db:
                await world.inventory(db).add_room(world.staff, category.public_id, label="201")
        except LabelTakenError:
            refused.append("201: label taken")
        return refused

    assert run(scenario) == ["A: label taken", "C: room full", "201: label taken"]


def test_rents_outside_the_rules_are_refused_by_the_service_and_the_database(
    run: Callable[..., Any],
) -> None:
    async def scenario(world: World) -> tuple[list[str], list[str]]:
        found = await _create(world, "Fictional Quarters", _away(950))
        refused = []
        try:
            async with world.sessions() as db:
                await world.inventory(db).add_room_category(
                    world.staff,
                    found.public_id,
                    CategoryDraft(
                        occupancy=Occupancy.SINGLE,
                        label="Single",
                        base_rent=rupees(16_000),
                        owner_max_rent=rupees(15_000),
                        security_deposit=Paise(-1),
                    ),
                )
        except ListingInvalidError as error:
            refused = error.problems
        broken = []
        overrides: dict[str, dict[str, Any]] = {
            "base_rent": {"base_rent_paise": 0},
            "owner_min_rent": {"base_rent_paise": 900_000, "owner_min_rent_paise": 1_000_000},
            "owner_max_rent": {"base_rent_paise": 900_000, "owner_max_rent_paise": 800_000},
            "security_deposit": {"security_deposit_paise": -1},
            "mandatory_charges": {"mandatory_charges": {"not": "a list"}},
        }
        for name, values in overrides.items():
            row = {
                "public_id": uuid.uuid7(),
                "property_id": found.id,
                "occupancy": "single",
                "ac": False,
                "attached_bath": False,
                "balcony": False,
                "label": "Broken",
                "base_rent_paise": 900_000,
                "security_deposit_paise": 0,
                "mandatory_charges": [],
                "status": "active",
            } | values
            async with world.sessions() as db:
                try:
                    await db.execute(insert(RoomCategory).values(row))
                except IntegrityError as error:
                    if f"ck_room_categories_{name}" in str(error):
                        broken.append(name)
        return refused, broken

    refused, broken = run(scenario)

    assert len(refused) == 2
    assert broken == [
        "base_rent",
        "owner_min_rent",
        "owner_max_rent",
        "security_deposit",
        "mandatory_charges",
    ]


def test_charges_are_stored_as_they_were_given(run: Callable[..., Any]) -> None:
    async def scenario(world: World) -> RoomCategory | None:
        found = await _create(world, "Fictional Abode", _away(1_000))
        async with world.sessions() as db:
            category = await world.inventory(db).add_room_category(
                world.staff, found.public_id, DOUBLE
            )
        async with world.sessions() as db:
            return await CatalogRepository(db).category(category.public_id)

    stored = run(scenario)

    assert stored is not None
    assert charges_from_json(stored.mandatory_charges) == DOUBLE.mandatory_charges
    assert (stored.base_rent_paise, stored.owner_min_rent_paise, stored.owner_max_rent_paise) == (
        1_200_000,
        1_100_000,
        1_500_000,
    )


def test_amenities_are_replaced_and_unknown_ones_refused(run: Callable[..., Any]) -> None:
    async def scenario(world: World) -> tuple[list[str], list[str], bool]:
        found = await _create(world, "Fictional Den", _away(1_050))
        async with world.sessions() as db:
            await world.listings(db).set_amenities(world.staff, found.public_id, ["wifi", "cctv"])
        async with world.sessions() as db:
            kept = await world.listings(db).set_amenities(
                world.staff, found.public_id, ["power-backup", "wifi"]
            )
        async with world.sessions() as db:
            stored = await CatalogRepository(db).amenities_of(found.id)
        try:
            async with world.sessions() as db:
                await world.listings(db).set_amenities(world.staff, found.public_id, ["moat"])
        except ListingInvalidError:
            return kept, stored, True
        return kept, stored, False

    assert run(scenario) == (["power-backup", "wifi"], ["power-backup", "wifi"], True)


def test_listing_details_are_checked_before_anything_is_written(run: Callable[..., Any]) -> None:
    async def scenario(world: World) -> list[str]:
        outcomes = []
        outside = _draft(world.owner, "Fictional Elsewhere", Point(lat=19.07, lng=72.87))
        for draft in (outside, _draft(world.owner, " ", _away(1_100))):
            try:
                async with world.sessions() as db:
                    await world.listings(db).create_property(world.staff, draft)
            except ListingInvalidError as error:
                outcomes.append(error.problems[0])
        unknown = replace(_draft(world.owner, "Fictional", _away(1_100)), locality="atlantis")
        try:
            async with world.sessions() as db:
                await world.listings(db).create_property(world.staff, unknown)
        except NotFoundError:
            outcomes.append("unknown locality")
        return outcomes

    assert run(scenario) == [
        "the location is outside Delhi NCR",
        "the name is required",
        "unknown locality",
    ]


def test_geo_queries_use_display_points_and_published_listings(
    run: Callable[..., Any],
) -> None:
    async def scenario(world: World) -> dict[str, Any]:
        near = await _move(
            world,
            await _sellable(world, await _create(world, "Near", _away(300))),
            PropertyStatus.PUBLISHED,
        )
        middle = await _move(
            world,
            await _sellable(world, await _create(world, "Middle", _away(900))),
            PropertyStatus.PUBLISHED,
        )
        draft = await _create(world, "Draft", _away(1_500))
        far = await _move(
            world,
            await _sellable(world, await _create(world, "Far", _away(2_600))),
            PropertyStatus.PUBLISHED,
        )
        mine = {near.public_id, middle.public_id, draft.public_id, far.public_id}
        centre = CAMPUS.location.point
        async with world.sessions() as db:
            catalog = CatalogRepository(db)
            within = [
                (nearby.property.public_id, nearby.distance_m)
                for nearby in await catalog.within(centre, 2_000)
                if nearby.property.public_id in mine
            ]
            with_drafts = {
                nearby.property.public_id
                for nearby in await catalog.within(
                    centre, 2_000, statuses=(PropertyStatus.PUBLISHED, PropertyStatus.DRAFT)
                )
            }
            box = Bounds(
                south=centre.lat - 0.005,
                west=centre.lng,
                north=centre.lat + 0.005,
                east=centre.lng + 0.015,
            )
            in_box = {found.public_id for found in await catalog.in_bounds(box)} & mine
            twins = {found.public_id for found in await catalog.near_exact(_away(310), 30)}
            displays = {
                found.public_id: (await catalog.points(found.id))[1] for found in (near, middle)
            }
        return {
            "within": within,
            "with_drafts": with_drafts & mine,
            "in_box": in_box,
            "twins": twins & mine,
            "ids": (near.public_id, middle.public_id, draft.public_id, far.public_id),
            "displays": displays,
        }

    found = run(scenario)
    near, middle, draft, _far = found["ids"]

    assert [listing for listing, _ in found["within"]] == [near, middle]
    for listing, metres in found["within"]:
        # Measured from the display point: never the exact distance.
        expected = distance_m(CAMPUS.location.point, found["displays"][listing])
        assert metres == pytest.approx(expected, rel=0.005)
    assert found["with_drafts"] == {near, middle, draft}
    assert found["in_box"] == {near, middle}
    assert found["twins"] == {near}
