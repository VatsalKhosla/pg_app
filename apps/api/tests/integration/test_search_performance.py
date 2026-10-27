"""Search's speed (step 3.2, ADR 0028): BUILD_PLAN asks for p95 under 300 ms on a seeded set of
3,000 properties. The listings are fictional, scattered around the seeded campuses, in a database
of their own so the other tests never see them.
"""

import asyncio
import logging
import random
import statistics
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any, Final

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.core.actor import Role
from app.core.calendar import india_date
from app.core.postgis import point_wkt
from app.modules.catalog.domain.location import Offset, moved, random_offset
from app.modules.catalog.models import Amenity, Owner, Property, RoomCategory
from app.modules.geo.models import Locality
from app.modules.identity.repository import UserRepository
from app.modules.search.domain.summaries import months_from
from app.modules.search.models import PropertyPriceSummary, SearchListing
from tests.integration.conftest import alembic_config, execute_autocommit
from tests.staff_api import DATA, Staff, phone, run_as_staff

pytestmark = pytest.mark.integration

LISTINGS: Final = 3_000
SEARCHES: Final = 200
P95_LIMIT_MS: Final = 300
FIRST_WORDS: Final = ("Shanti", "Sunrise", "Green", "Royal", "Comfort", "Lotus", "Silver", "Tulip")
SECOND_WORDS: Final = ("PG", "Residency", "Stay", "Homes", "Niwas", "House")


@pytest.fixture
def own_database_url(postgres_url: str) -> Iterator[str]:
    """A database of this test's own, migrated, and dropped afterwards."""
    from alembic import command  # noqa: PLC0415 - only this fixture migrates

    name = f"search_speed_{uuid.uuid4().hex[:12]}"
    asyncio.run(execute_autocommit(postgres_url, f'CREATE DATABASE "{name}"'))
    url = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    try:
        command.upgrade(alembic_config(url), "head")
        yield url
    finally:
        asyncio.run(execute_autocommit(postgres_url, f'DROP DATABASE "{name}" WITH (FORCE)'))


async def _seed(ops: Staff, rng: random.Random) -> None:
    """3,000 live listings with three room categories each, and their search entries and price
    summaries, written straight into the tables: only the search query is being timed."""
    app, now = ops.app, ops.app.state.clock.now()
    campuses = [campus.location.point for campus in DATA.campuses]
    months = months_from(india_date(now))
    async with app.state.sessionmaker() as db, db.begin():
        user = await UserRepository(db).add(phone_e164=f"+91{phone()}", roles=(Role.OWNER,))
        owner_id = (
            await db.execute(
                insert(Owner)
                .values(
                    user_id=user.id,
                    legal_name="Fictional Stays LLP",
                    business_name="Fictional Stays",
                    kyc_status="not_started",
                    status="active",
                )
                .returning(Owner.id)
            )
        ).scalar_one()
        localities = list(await db.execute(select(Locality.id, Locality.slug, Locality.name)))
        amenities = list(await db.scalars(select(Amenity.slug)))
        places = []
        for index in range(LISTINGS):
            exact = moved(
                rng.choice(campuses),
                Offset(bearing_deg=rng.uniform(0, 360), distance_m=rng.uniform(100, 6_000)),
            )
            places.append((exact, moved(exact, random_offset(rng)), rng.choice(localities), index))
        properties = list(
            await db.execute(
                insert(Property).returning(
                    Property.id,
                    Property.public_id,
                    Property.name,
                    Property.gender_policy,
                    Property.meals,
                    Property.licence_status,
                    Property.published_at,
                    sort_by_parameter_order=True,
                ),
                [
                    {
                        "public_id": uuid.uuid7(),
                        "owner_id": owner_id,
                        "locality_id": locality.id,
                        "slug": f"speed-{index}",
                        "name": f"{rng.choice(FIRST_WORDS)} {rng.choice(SECOND_WORDS)} {index}",
                        "description": "",
                        "address_line": "A fictional lane",
                        "location": point_wkt(exact),
                        "display_location": point_wkt(display),
                        "location_precision": "exact",
                        "gender_policy": rng.choice(("boys", "girls", "coed")),
                        "meals": rng.choice(("none", "breakfast", "two", "three")),
                        "house_rules": [],
                        "verification_status": "verified",
                        "licence_status": rng.choice(("unknown", "licensed")),
                        "society_permission": "n/a",
                        "instant_confirm": False,
                        "status": "published",
                        "published_at": now - timedelta(minutes=index),
                    }
                    for exact, display, locality, index in places
                ],
            )
        )
        await db.execute(
            insert(SearchListing),
            [
                {
                    "property_id": row.id,
                    "public_id": row.public_id,
                    "slug": f"speed-{index}",
                    "name": row.name,
                    "locality_id": locality.id,
                    "locality_slug": locality.slug,
                    "locality_name": locality.name,
                    "display_location": point_wkt(display),
                    "gender_policy": row.gender_policy,
                    "meals": row.meals,
                    "verified": True,
                    "licensed": row.licence_status == "licensed",
                    "amenities": sorted(rng.sample(amenities, k=rng.randint(0, 6))),
                    "media_ids": [],
                    "published_at": row.published_at,
                    "refreshed_at": now,
                }
                for row, (_, display, locality, index) in zip(properties, places, strict=True)
            ],
        )
        categories = []
        for row in properties:
            for occupancy in rng.sample(("single", "double", "triple", "quad"), k=3):
                rent = rng.randrange(600_000, 2_500_000, 50_000)
                categories.append(
                    {
                        "public_id": uuid.uuid7(),
                        "property_id": row.id,
                        "occupancy": occupancy,
                        "ac": rng.random() < 0.4,
                        "attached_bath": rng.random() < 0.3,
                        "balcony": False,
                        "label": f"{occupancy.title()} sharing",
                        "base_rent_paise": rent,
                        "security_deposit_paise": rent,
                        "mandatory_charges": [],
                        "status": "active",
                    }
                )
        made = list(
            await db.execute(
                insert(RoomCategory).returning(
                    RoomCategory.id,
                    RoomCategory.property_id,
                    RoomCategory.occupancy,
                    RoomCategory.ac,
                    RoomCategory.attached_bath,
                    RoomCategory.base_rent_paise,
                ),
                categories,
            )
        )
        await db.execute(
            insert(PropertyPriceSummary),
            [
                {
                    "property_id": category.property_id,
                    "room_category_id": category.id,
                    "month": month,
                    "min_rent_paise": category.base_rent_paise,
                    "max_rent_paise": category.base_rent_paise,
                    "available_beds": rng.randint(0, 4),
                    "occupancy": category.occupancy,
                    "ac": category.ac,
                    "attached_bath": category.attached_bath,
                    "computed_at": now,
                }
                for category in made
                for month in months
            ],
        )
    # As autovacuum would, so the planner knows the tables' sizes.
    async with app.state.engine.begin() as connection:
        await connection.execute(text("ANALYZE search_listings, property_price_summaries"))


def _searches(rng: random.Random) -> list[dict[str, Any]]:
    campuses = [campus.slug for campus in DATA.campuses]
    localities = [locality.slug for locality in DATA.localities]
    kinds: list[Callable[[], dict[str, Any]]] = [
        lambda: {"campus": rng.choice(campuses), "sort": "distance"},
        lambda: {"campus": rng.choice(campuses), "radius_m": 5_000, "sort": "price_asc"},
        lambda: {
            "campus": rng.choice(campuses),
            "budget_min_paise": 800_000,
            "budget_max_paise": 1_500_000,
            "occupancy": rng.choice(("single", "double", "triple")),
        },
        lambda: {"locality": rng.choice(localities), "sort": "newest"},
        lambda: {"gender": rng.choice(("boys", "girls")), "ac": "true", "sort": "price_desc"},
        lambda: {"meals": "three", "attached_bath": "true", "available": "true"},
        lambda: {"amenities": ["wifi", "cctv"], "campus": rng.choice(campuses)},
        lambda: {"q": rng.choice(FIRST_WORDS).lower()},
        lambda: {"q": f"{rng.choice(FIRST_WORDS)} {rng.choice(SECOND_WORDS)}"},
        lambda: {"bbox": "77.15,28.64,77.25,28.72", "sort": "price_asc"},
        lambda: {"move_in_month": None, "campus": rng.choice(campuses), "limit": 50},
    ]
    return [
        {key: value for key, value in rng.choice(kinds)().items() if value} for _ in range(SEARCHES)
    ]


def test_search_answers_within_300_ms_at_the_95th_percentile_over_3000_listings(
    make_settings: Callable[..., Settings], own_database_url: str, valkey_url: str
) -> None:
    rng = random.Random(2027)  # noqa: S311 - fictional test data, the same every run

    async def scenario(ops: Staff) -> list[tuple[float, dict[str, Any]]]:
        await _seed(ops, rng)
        timings: list[tuple[float, dict[str, Any]]] = []
        searches = _searches(rng)
        # The first few warm the connection pool and the planner's caches.
        for params in searches[:5]:
            await ops.client.get("/v1/search/properties", params=params)
        for params in searches:
            started = time.perf_counter()
            response = await ops.client.get("/v1/search/properties", params=params)
            timings.append(((time.perf_counter() - started) * 1_000, params))
            assert response.status_code == 200, response.text
            next_cursor = response.json()["nextCursor"]
            if next_cursor is not None and rng.random() < 0.25:
                started = time.perf_counter()
                page = await ops.client.get(
                    "/v1/search/properties", params=params | {"cursor": next_cursor}
                )
                timings.append(((time.perf_counter() - started) * 1_000, params | {"page": 2}))
                assert page.status_code == 200, page.text
        return timings

    settings = make_settings(database_url=own_database_url, redis_url=valkey_url)
    found = run_as_staff(settings, scenario)

    timings = [milliseconds for milliseconds, _ in found]
    p95 = statistics.quantiles(timings, n=20)[-1]
    slowest = sorted(found, key=lambda each: each[0], reverse=True)[:5]
    logging.getLogger(__name__).info(
        "search over %d listings: median %.0f ms, p95 %.0f ms, %d searches",
        LISTINGS,
        statistics.median(timings),
        p95,
        len(timings),
    )
    assert p95 < P95_LIMIT_MS, (
        f"p95 {p95:.0f} ms (median {statistics.median(timings):.0f} ms) over {len(timings)}"
        f" searches; slowest: {[(round(ms), params) for ms, params in slowest]}"
    )
