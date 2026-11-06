"""Thousands of fictional listings written straight into the tables search reads: the search
performance test's data (step 3.2) and the load tests' (step 8.2, `python -m tests.load.seed`).
Everything is fictional: invented names, points scattered around the seeded campuses, made-up
rents. Nothing here goes through the services, so only searching and the map are realistic on it.
"""

import random
import uuid
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.actor import Role
from app.core.calendar import india_date
from app.core.postgis import point_wkt
from app.modules.catalog.domain.location import Offset, moved, random_offset
from app.modules.catalog.models import Amenity, Owner, Property, RoomCategory
from app.modules.geo.models import Locality
from app.modules.identity.repository import UserRepository
from app.modules.search.domain.summaries import months_from
from app.modules.search.models import PropertyPriceSummary, SearchListing
from tests.staff_api import DATA, phone

FIRST_WORDS: Final = ("Shanti", "Sunrise", "Green", "Royal", "Comfort", "Lotus", "Silver", "Tulip")
SECOND_WORDS: Final = ("PG", "Residency", "Stay", "Homes", "Niwas", "House")


async def add_listings(
    sessionmaker: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    *,
    now: datetime,
    rng: random.Random,
    count: int,
) -> None:
    """``count`` live listings with three room categories each, and their search entries and price
    summaries, under one fictional owner."""
    campuses = [campus.location.point for campus in DATA.campuses]
    months = months_from(india_date(now))
    async with sessionmaker() as db, db.begin():
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
        for index in range(count):
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
    async with engine.begin() as connection:
        await connection.execute(text("ANALYZE search_listings, property_price_summaries"))
