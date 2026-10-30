"""Fictional sample PGs for local development (``make seed``; step 3.4, ADR 0030): live listings to
try the PG page, search and the map on, built through the same services ops and field agents use,
photos included. A composition root, like app/jobs.py: it calls several modules' services.

Everything here is fictional: the names say so, the owners' numbers are random, the photos are
plain colours with "Fictional sample" written on them, and the places are only offsets from the
seeded campuses. ``python -m app.manage catalog samples`` refuses to run in production, so none
of it reaches the live site (CLAUDE.md: never invent real-world data). Staging has them, under a
banner saying they're fictional (ADR 0047).
"""

import io
import secrets
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select

from app.core.actor import Actor, Role
from app.core.flags import FeatureFlags
from app.core.money import Paise
from app.modules.catalog.domain.charges import (
    ChargeKind,
    MandatoryCharge,
    MeteredCharge,
    MonthlyCharge,
    OneTimeCharge,
)
from app.modules.catalog.domain.listing import (
    GenderPolicy,
    LocationPrecision,
    Meals,
    PropertyStatus,
    SocietyPermission,
)
from app.modules.catalog.domain.location import Offset, moved
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.catalog.domain.verification import (
    Checklist,
    Condition,
    Cracks,
    VisitResult,
    WomenSafety,
)
from app.modules.catalog.models import Property
from app.modules.catalog.service import (
    CategoryDraft,
    InventoryService,
    ListingService,
    OwnerService,
    PropertyDraft,
    Report,
    VerificationService,
)
from app.modules.geo.service import GeoLookup
from app.modules.identity.repository import UserRepository
from app.modules.media.domain.assets import Purpose
from app.modules.media.service import MediaService, process_upload, upload_key

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.clock import Clock
    from app.core.geometry import Point
    from app.modules.media.ports import ObjectStorage
    from app.modules.media.service import Buckets

# Every sample's name starts so, which is how a second run knows they're there.
NAME_PREFIX: Final = "Fictional Sample PG"
# The advisory lock one run holds while it makes the samples.
LOCK: Final = "catalog:samples"
PHOTOS_PER_LISTING: Final = 3


@dataclass(frozen=True, slots=True)
class Category:
    occupancy: Occupancy
    rupees: int
    ac: bool
    attached_bath: bool
    rooms: int


@dataclass(frozen=True, slots=True)
class Sample:
    name: str
    locality: str
    # Where it is: this far from that campus, this way.
    campus: str
    bearing_deg: float
    distance_m: float
    gender: GenderPolicy
    meals: Meals
    categories: tuple[Category, ...]
    amenities: tuple[str, ...]
    colour: tuple[int, int, int]


SAMPLES: Final = (
    Sample(
        f"{NAME_PREFIX} Aster",
        "kamla-nagar",
        "hindu-college",
        35,
        650,
        GenderPolicy.GIRLS,
        Meals.TWO,
        (
            Category(Occupancy.DOUBLE, 12_500, ac=True, attached_bath=False, rooms=2),
            Category(Occupancy.TRIPLE, 9_000, ac=False, attached_bath=False, rooms=1),
        ),
        ("wifi", "power-backup", "ro-water", "cctv", "warden"),
        (46, 125, 116),
    ),
    Sample(
        f"{NAME_PREFIX} Banyan",
        "vijay-nagar",
        "miranda-house",
        300,
        900,
        GenderPolicy.BOYS,
        Meals.THREE,
        (
            Category(Occupancy.SINGLE, 18_000, ac=True, attached_bath=True, rooms=3),
            Category(Occupancy.DOUBLE, 13_000, ac=False, attached_bath=False, rooms=2),
        ),
        ("wifi", "laundry", "gym", "hot-water"),
        (142, 98, 52),
    ),
    Sample(
        f"{NAME_PREFIX} Cedar",
        "malka-ganj",
        "kirori-mal-college",
        140,
        1_200,
        GenderPolicy.COED,
        Meals.TWO,
        (Category(Occupancy.DOUBLE, 11_000, ac=False, attached_bath=True, rooms=2),),
        ("wifi", "housekeeping", "study-area"),
        (84, 72, 140),
    ),
    Sample(
        f"{NAME_PREFIX} Deodar",
        "satya-niketan",
        "sri-venkateswara-college",
        60,
        500,
        GenderPolicy.GIRLS,
        Meals.BREAKFAST,
        (
            Category(Occupancy.TRIPLE, 8_500, ac=False, attached_bath=False, rooms=2),
            Category(Occupancy.DOUBLE, 10_500, ac=True, attached_bath=False, rooms=1),
        ),
        ("wifi", "ro-water", "secure-entry"),
        (60, 110, 160),
    ),
    Sample(
        f"{NAME_PREFIX} Elm",
        "moti-bagh",
        "jesus-and-mary-college",
        220,
        800,
        GenderPolicy.BOYS,
        Meals.NONE,
        (Category(Occupancy.SINGLE, 15_000, ac=False, attached_bath=True, rooms=2),),
        ("wifi", "parking"),
        (120, 120, 60),
    ),
    Sample(
        f"{NAME_PREFIX} Fern",
        "anand-niketan",
        "aryabhatta-college",
        10,
        700,
        GenderPolicy.COED,
        Meals.THREE,
        (
            Category(Occupancy.QUAD, 7_500, ac=False, attached_bath=False, rooms=1),
            Category(Occupancy.DOUBLE, 12_000, ac=True, attached_bath=True, rooms=1),
        ),
        ("wifi", "power-backup", "common-room"),
        (150, 70, 90),
    ),
)

_BEDS: Final = {Occupancy.SINGLE: 1, Occupancy.DOUBLE: 2, Occupancy.TRIPLE: 3, Occupancy.QUAD: 4}


def _charges(category: Category) -> tuple[MandatoryCharge, ...]:
    """What every sample room adds to its rent: upkeep, a deposit-free registration, and metered
    electricity where there's AC. Fictional amounts."""
    charges: list[MandatoryCharge] = [
        MonthlyCharge(kind=ChargeKind.MAINTENANCE, label="Maintenance", amount=Paise(50_000)),
        OneTimeCharge(kind=ChargeKind.REGISTRATION, label="Registration", amount=Paise(100_000)),
    ]
    if category.ac:
        charges.append(
            MeteredCharge(
                kind=ChargeKind.ELECTRICITY,
                label="Electricity",
                rate=Paise(900),
                unit="kWh",
                monthly_estimate=Paise(80_000),
            )
        )
    return tuple(charges)


def photo(colour: tuple[int, int, int], caption: str) -> bytes:
    """A JPEG 1200 by 800: a plain colour, getting darker downwards, with ``caption`` on it."""
    image = Image.new("RGB", (1200, 800), colour)
    draw = ImageDraw.Draw(image)
    for row in range(800):
        shade = tuple(max(0, value - row // 12) for value in colour)
        draw.line([(0, row), (1200, row)], fill=shade)
    font = ImageFont.load_default(size=56)
    draw.text((80, 640), caption, fill=(255, 255, 255), font=font)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


def _phone() -> str:
    """A random Indian mobile number, for a fictional account no message is ever sent to."""
    return f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"


class SampleBuilder:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        clock: Clock,
        *,
        storage: ObjectStorage,
        buckets: Buckets,
        say: Callable[[str], object],
        samples: Sequence[Sample] = SAMPLES,
    ) -> None:
        self._sessions = sessionmaker
        self._clock = clock
        self._storage = storage
        self._buckets = buckets
        self._flags = FeatureFlags(sessionmaker, clock)
        self._say = say
        self._samples = samples

    async def build(self) -> list[str]:
        """The samples, unless they're there already: their slugs.

        One run at a time: a run started meanwhile (by a second browser-test worker, say) waits
        for this one, then finds the samples there. The lock is held by a transaction of its own,
        open until the samples are made.
        """
        async with self._sessions() as guard, guard.begin():
            await guard.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(LOCK, 0))))
            if await _samples_exist(guard):
                self._say("The sample listings are there already.")
                return []
            ops = await self._staff(Role.OPS, "Sample data ops (fictional)")
            agent = await self._staff(Role.FIELD_AGENT, "Sample data field agent (fictional)")
            return [await self._listing(sample, ops=ops, agent=agent) for sample in self._samples]

    async def _staff(self, role: Role, name: str) -> Actor:
        async with self._sessions() as db, db.begin():
            user = await UserRepository(db).add(phone_e164=_phone(), roles=(role,))
            user.name = name
        return Actor(
            user_id=user.id,
            user_public_id=user.public_id,
            roles=frozenset({role}),
            session_id=0,
            session_public_id=uuid.uuid7(),
        )

    async def _listing(self, sample: Sample, *, ops: Actor, agent: Actor) -> str:
        at = await self._place(sample)
        async with self._sessions() as db:
            owner = await OwnerService(db, self._clock).add(
                ops,
                phone=_phone()[3:],
                legal_name=f"{sample.name.removeprefix(NAME_PREFIX).strip()} Stays LLP",
                business_name=f"{sample.name.removeprefix(NAME_PREFIX).strip()} Stays",
                name="A Fictional Owner",
            )
        async with self._sessions() as db:
            listing = await self._listings(db).create_property(
                ops,
                PropertyDraft(
                    owner=owner.owner.public_id,
                    locality=sample.locality,
                    name=sample.name,
                    address_line="House 1, a fictional lane",
                    location=at,
                    location_precision=LocationPrecision.EXACT,
                    gender_policy=sample.gender,
                    meals=sample.meals,
                    description=(
                        "A fictional sample PG, for trying the site out on your own machine."
                        " It isn't real, and neither are its rooms, prices or owner."
                    ),
                    house_rules=("No smoking indoors", "Guests until 9 pm"),
                    society_permission=SocietyPermission.NOT_APPLICABLE,
                ),
            )
        for category in sample.categories:
            await self._category(listing.public_id, category, ops=ops)
        async with self._sessions() as db:
            await self._listings(db).set_amenities(ops, listing.public_id, sample.amenities)
        photos = [
            await self._upload(
                ops,
                Purpose.LISTING_PHOTO,
                photo(sample.colour, f"Fictional sample photo {index + 1}"),
            )
            for index in range(PHOTOS_PER_LISTING)
        ]
        async with self._sessions() as db:
            await self._listings(db).set_media(ops, listing.public_id, photos)
        await self._verify(listing.public_id, at, sample, ops=ops, agent=agent)
        async with self._sessions() as db:
            published = await self._listings(db).move(
                ops, listing.public_id, PropertyStatus.PUBLISHED
            )
        self._say(f"{published.slug}  {sample.name}")
        return published.slug

    def _listings(self, db: AsyncSession) -> ListingService:
        return ListingService(db, self._clock, buckets=self._buckets, flags=self._flags)

    async def _place(self, sample: Sample) -> Point:
        async with self._sessions() as db, db.begin():
            campus = await GeoLookup(db).campus(sample.campus)
        if campus is None:  # pragma: no cover - the seeded campuses are loaded first
            msg = f"no campus {sample.campus}: run `make seed` (geo load) first"
            raise LookupError(msg)
        return moved(
            campus.location,
            Offset(bearing_deg=sample.bearing_deg, distance_m=sample.distance_m),
        )

    async def _category(self, listing: uuid.UUID, category: Category, *, ops: Actor) -> None:
        rent = Paise(category.rupees * 100)
        async with self._sessions() as db:
            added = await InventoryService(db, self._clock).add_room_category(
                ops,
                listing,
                CategoryDraft(
                    occupancy=category.occupancy,
                    label=f"{category.occupancy.value.title()} sharing"
                    + (", AC" if category.ac else ""),
                    base_rent=rent,
                    security_deposit=rent,
                    ac=category.ac,
                    attached_bath=category.attached_bath,
                    mandatory_charges=_charges(category),
                ),
            )
        for room in range(category.rooms):
            async with self._sessions() as db:
                await InventoryService(db, self._clock).add_room(
                    ops,
                    added.public_id,
                    label=f"{category.occupancy.value[0].upper()}{room + 1:02d}",
                    floor=room // 2,
                    beds=_BEDS[category.occupancy],
                )

    async def _upload(self, actor: Actor, purpose: Purpose, body: bytes) -> uuid.UUID:
        """A photo, uploaded and processed as the browser and the worker would."""
        async with self._sessions() as db:
            started = await self._media(db).start_upload(
                actor, purpose=purpose, content_type="image/jpeg", byte_size=len(body)
            )
        media_id = started.asset.public_id
        await self._storage.upload(
            self._buckets.private, upload_key(media_id), body, content_type="image/jpeg"
        )
        async with self._sessions() as db:
            await self._media(db).finish_upload(actor, media_id)
        async with self._sessions() as db, db.begin():
            await process_upload(
                db, self._clock, storage=self._storage, buckets=self._buckets, media_id=media_id
            )
        return media_id

    def _media(self, db: AsyncSession) -> MediaService:
        return MediaService(db, self._clock, storage=self._storage, buckets=self._buckets)

    async def _verify(
        self, listing: uuid.UUID, at: Point, sample: Sample, *, ops: Actor, agent: Actor
    ) -> None:
        """A field agent's visit, booked by ops and passed, with a photo as evidence."""
        evidence = await self._upload(
            agent,
            Purpose.VERIFICATION_PHOTO,
            photo(sample.colour, "Fictional sample: verification"),
        )
        async with self._sessions() as db:
            visit = await VerificationService(db, self._clock, buckets=self._buckets).schedule(
                ops, listing, agent=agent.user_public_id, scheduled_for=self._clock.now()
            )
        async with self._sessions() as db:
            await VerificationService(db, self._clock, buckets=self._buckets).submit(
                agent,
                visit.public_id,
                Report(
                    checklist=Checklist(
                        building_age_years=None,
                        condition=Condition.GOOD,
                        cracks=Cracks.NONE,
                        exits=2,
                        fire_extinguishers=True,
                        cctv=True,
                        warden=sample.gender is not GenderPolicy.BOYS,
                        women_safety=frozenset({WomenSafety.SECURE_ENTRY, WomenSafety.LIT_APPROACH})
                        if sample.gender is not GenderPolicy.BOYS
                        else frozenset(),
                        licence_number=None,
                        society_permission=SocietyPermission.NOT_APPLICABLE,
                        authority_notice=False,
                    ),
                    result=VisitResult.PASSED,
                    notes="",
                    position=at,
                    accuracy_m=8.0,
                    photos=(evidence,),
                ),
            )


async def _samples_exist(db: AsyncSession) -> bool:
    found = await db.scalar(
        select(Property.id).where(Property.name.startswith(NAME_PREFIX)).limit(1)
    )
    return found is not None
