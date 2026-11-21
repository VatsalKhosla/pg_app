"""Owners and their PGs from a filled-in template (ADR 0072): checked first, then made through the
same services the ops console uses, so every rule they keep holds here too.

Each PG goes its own way: its owner is added, or found by their phone; its listing is made as a
draft, never published, with its room types and amenities; and a PG without a pin waits for ops
to add it from the console. Running the same file again makes nothing twice: an owner is found,
and a PG of the same name for that owner is left alone. Personal data stays in the request:
nothing here logs a phone number or an address.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal

import structlog

from app.core.errors import AppError
from app.core.geometry import Point
from app.core.money import Paise
from app.modules.catalog.domain.listing import LocationPrecision
from app.modules.catalog.domain.listing_import import ImportedPg, parse_listing_import
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.service.inventory import CategoryDraft, InventoryService
from app.modules.catalog.service.listings import ListingService, PropertyDraft
from app.modules.catalog.service.owners import OwnerService
from app.modules.geo.service import GeoLookup
from app.modules.identity.service import Accounts

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.flags import FlagReader
    from app.modules.media.service import Buckets

logger = structlog.stdlib.get_logger(__name__)

OwnerOutcome = Literal["new", "existing", "failed"]
ListingOutcome = Literal["new", "exists", "needs_pin", "failed", "skipped"]
# What the file says about where a PG is: the owner's own pin, not yet checked on the spot.
IMPORTED_PRECISION: Final = LocationPrecision.APPROXIMATE


@dataclass(frozen=True, slots=True)
class PgOutcome:
    row: int
    name: str
    owner_name: str
    owner: OwnerOutcome
    listing: ListingOutcome
    # The listing's id once it exists (made now, or found).
    listing_id: uuid.UUID | None
    room_types: int
    problems: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportReport:
    # False for a check, which makes nothing.
    done: bool
    pgs: tuple[PgOutcome, ...]
    # Rows that couldn't be read at all, and why.
    problems: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class _Known:
    owner_public_id: uuid.UUID | None
    listing_id: uuid.UUID | None
    problems: tuple[str, ...]


class ListingImport:
    def __init__(
        self, db: AsyncSession, clock: Clock, *, buckets: Buckets, flags: FlagReader
    ) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogRepository(db)
        self._accounts = Accounts(db)
        self._geo = GeoLookup(db)
        self._owners = OwnerService(db, clock)
        self._listings = ListingService(db, clock, buckets=buckets, flags=flags)
        self._inventory = InventoryService(db, clock)

    async def check(self, text: str) -> ImportReport:
        """What the file would make, and what's wrong with it, making nothing."""
        parsed = parse_listing_import(text)
        outcomes = []
        for pg in parsed.pgs:
            known = await self._known(pg)
            outcomes.append(_planned(pg, known))
        return ImportReport(done=False, pgs=tuple(outcomes), problems=parsed.problems)

    async def run(self, actor: Actor, text: str) -> ImportReport:
        """Make what the file describes, PG by PG; one that fails leaves the others be."""
        parsed = parse_listing_import(text)
        outcomes = []
        for pg in parsed.pgs:
            known = await self._known(pg)
            if known.problems:
                outcomes.append(_planned(pg, known))
                continue
            outcomes.append(await self._make(actor, pg, known))
        made = sum(1 for outcome in outcomes if outcome.listing == "new")
        logger.info("listing import", pgs=len(outcomes), listings_made=made)
        return ImportReport(done=True, pgs=tuple(outcomes), problems=parsed.problems)

    async def _known(self, pg: ImportedPg) -> _Known:
        """The owner and the listing that exist already, and what the file gets wrong that only
        the database can tell."""
        problems = []
        async with self._db.begin():
            if await self._geo.locality(pg.locality) is None:
                problems.append(f"no such locality: {pg.locality}")
            if pg.amenities:
                ids = await self._catalog.amenity_ids(set(pg.amenities))
                if unknown := sorted(set(pg.amenities) - ids.keys()):
                    problems.append(f"no such amenity: {', '.join(unknown)}")
            account = await self._accounts.find(pg.owner_phone)
            owner = None if account is None else await self._catalog.owner_of_user(account.id)
            listing = None
            if owner is not None:
                name = pg.name.casefold()
                for row in await self._catalog.properties_of_owner(owner.id):
                    if row.name.casefold() == name:
                        listing = row.public_id
        return _Known(
            owner_public_id=None if owner is None else owner.public_id,
            listing_id=listing,
            problems=tuple(problems),
        )

    async def _make(self, actor: Actor, pg: ImportedPg, known: _Known) -> PgOutcome:
        owner_outcome: OwnerOutcome = "existing"
        owner_id = known.owner_public_id
        if owner_id is None:
            try:
                record = await self._owners.add(
                    actor,
                    phone=pg.owner_phone,
                    legal_name=pg.legal_name,
                    business_name=pg.business_name,
                    name=pg.owner_name,
                    email=pg.owner_email,
                )
            except AppError as failure:
                return _failed(pg, "failed", "skipped", failure)
            owner_id, owner_outcome = record.owner.public_id, "new"
        if known.listing_id is not None:
            return _outcome(pg, owner_outcome, "exists", known.listing_id)
        if pg.location is None:
            return _outcome(pg, owner_outcome, "needs_pin", None)
        lat, lng = pg.location
        try:
            made = await self._listings.create_property(
                actor,
                PropertyDraft(
                    owner=owner_id,
                    locality=pg.locality,
                    name=pg.name,
                    address_line=pg.address,
                    location=Point(lat=lat, lng=lng),
                    location_precision=IMPORTED_PRECISION,
                    gender_policy=pg.gender_policy,
                    meals=pg.meals,
                    description=pg.description,
                    house_rules=pg.house_rules,
                ),
            )
        except AppError as failure:
            return _failed(pg, owner_outcome, "failed", failure)
        problems = []
        added = 0
        for room in pg.room_types:
            try:
                await self._inventory.add_room_category(
                    actor,
                    made.public_id,
                    CategoryDraft(
                        occupancy=room.occupancy,
                        label=room.label,
                        base_rent=Paise(room.rent_paise),
                        security_deposit=Paise(room.deposit_paise),
                        ac=room.ac,
                        attached_bath=room.attached_bath,
                        balcony=room.balcony,
                    ),
                )
                added += 1
            except AppError as failure:
                problems.append(f"{room.label}: {_reason(failure)}")
        if pg.amenities:
            try:
                await self._listings.set_amenities(actor, made.public_id, pg.amenities)
            except AppError as failure:
                problems.append(f"amenities: {_reason(failure)}")
        return PgOutcome(
            row=pg.row,
            name=pg.name,
            owner_name=pg.owner_name,
            owner=owner_outcome,
            listing="new",
            listing_id=made.public_id,
            room_types=added,
            problems=tuple(problems),
        )


def _reason(failure: AppError) -> str:
    return failure.detail or failure.title


def _planned(pg: ImportedPg, known: _Known) -> PgOutcome:
    """What a check says the file would make."""
    if known.problems:
        return PgOutcome(
            row=pg.row,
            name=pg.name,
            owner_name=pg.owner_name,
            owner="existing" if known.owner_public_id is not None else "new",
            listing="skipped",
            listing_id=known.listing_id,
            room_types=len(pg.room_types),
            problems=known.problems,
        )
    owner: OwnerOutcome = "existing" if known.owner_public_id is not None else "new"
    if known.listing_id is not None:
        return _outcome(pg, owner, "exists", known.listing_id)
    return _outcome(pg, owner, "needs_pin" if pg.location is None else "new", None)


def _outcome(
    pg: ImportedPg, owner: OwnerOutcome, listing: ListingOutcome, listing_id: uuid.UUID | None
) -> PgOutcome:
    return PgOutcome(
        row=pg.row,
        name=pg.name,
        owner_name=pg.owner_name,
        owner=owner,
        listing=listing,
        listing_id=listing_id,
        room_types=len(pg.room_types),
    )


def _failed(
    pg: ImportedPg, owner: OwnerOutcome, listing: ListingOutcome, failure: AppError
) -> PgOutcome:
    return PgOutcome(
        row=pg.row,
        name=pg.name,
        owner_name=pg.owner_name,
        owner=owner,
        listing=listing,
        listing_id=None,
        room_types=0,
        problems=(_reason(failure),),
    )
