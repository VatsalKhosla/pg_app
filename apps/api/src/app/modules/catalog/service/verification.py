"""Field verification (step 2.5, ADR 0024): ops book a visit for a field agent, the agent submits
the report on site, and the result sets the property's verification status.

A failed or suspended property that is live comes down at once (paused), audited like any
status change. The agent's position comes from their phone and the time from the server; the
distance from the pin is kept, and the agent may make their position the building's pin.
"""

import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from app.core.actor import Role
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.geometry import Point, distance_m
from app.core.pagination import split_page
from app.modules.catalog.domain.listing import PropertyStatus, VerificationStatus, can_move
from app.modules.catalog.domain.location import moved, random_offset
from app.modules.catalog.domain.verification import (
    MAX_DAYS_AHEAD,
    REASON_MAX_LENGTH,
    Checklist,
    VisitResult,
    VisitStatus,
    can_schedule,
    can_suspend,
    keeps_listing_live,
    report_problems,
    status_after,
)
from app.modules.catalog.errors import ListingInvalidError
from app.modules.catalog.models import VerificationVisit
from app.modules.catalog.repository import (
    CatalogRepository,
    VisitRepository,
    checklist_from_json,
    checklist_to_json,
)
from app.modules.catalog.service.checks import check, location_problems, text_problems
from app.modules.catalog.service.trail import staff_did
from app.modules.geo.service import GeoLookup
from app.modules.identity.service import Accounts
from app.modules.media.domain.assets import AssetStatus, Purpose
from app.modules.media.service import MediaLookup

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence
    from datetime import datetime
    from random import Random

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.pagination import PageRequest
    from app.modules.catalog.models import Property
    from app.modules.geo.service import LocalityRef
    from app.modules.identity.service import Account
    from app.modules.media.ports import ObjectStorage
    from app.modules.media.service import Buckets, MediaRef

# A visit may be booked a little in the past: the agent may be on site already.
SCHEDULE_GRACE = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class Report:
    checklist: Checklist
    result: VisitResult
    notes: str
    # Where the agent's phone said they were, and how sure it was.
    position: Point
    accuracy_m: float
    photos: Sequence[uuid.UUID] = field(default=())
    # Make the agent's position the building's pin (a new public point follows).
    move_pin: bool = False


@dataclass(frozen=True, slots=True)
class VisitProperty:
    property: Property
    locality: LocalityRef
    exact: Point
    owner_business: str
    owner_phone: str | None


@dataclass(frozen=True, slots=True)
class VisitView:
    visit: VerificationVisit
    property: VisitProperty
    agent: Account | None
    position: Point | None
    checklist: Checklist | None
    photos: tuple[MediaRef, ...]


def _reason_problems(reason: str) -> list[str]:
    return text_problems("the reason", reason, required=True, max_length=REASON_MAX_LENGTH)


class VerificationService:
    def __init__(
        self, db: AsyncSession, clock: Clock, *, buckets: Buckets, rng: Random | None = None
    ) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogRepository(db)
        self._visits = VisitRepository(db)
        self._accounts = Accounts(db)
        self._media = MediaLookup(db, buckets)
        # Display offsets must be unpredictable, so they come from the operating system.
        self._rng = rng or secrets.SystemRandom()

    async def schedule(
        self,
        actor: Actor,
        property_id: uuid.UUID,
        *,
        agent: uuid.UUID,
        scheduled_for: datetime,
    ) -> VerificationVisit:
        now = self._clock.now()
        if not now - SCHEDULE_GRACE <= scheduled_for <= now + timedelta(days=MAX_DAYS_AHEAD):
            raise ListingInvalidError(
                [f"a visit can be booked from now to {MAX_DAYS_AHEAD} days ahead"]
            )
        async with self._db.begin():
            found = await self._catalog.property(property_id, lock=True)
            if found is None:
                raise NotFoundError
            visitor = await self._accounts.active_with_role(agent, Role.FIELD_AGENT)
            if visitor is None:
                raise ListingInvalidError(["that person isn't an active field agent"])
            current = VerificationStatus(found.verification_status)
            if not can_schedule(current):
                raise InvalidTransitionError(f"A {current} property can't have a visit booked.")
            visit = await self._catalog.add(
                VerificationVisit(
                    property_id=found.id,
                    agent_id=visitor.id,
                    scheduled_by=actor.user_id,
                    scheduled_for=scheduled_for,
                    status=VisitStatus.SCHEDULED,
                    status_before=current,
                )
            )
            found.verification_status = VerificationStatus.SCHEDULED
            await self._db.flush()
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.verification_scheduled",
                entity="verification_visit",
                entity_id=visit.public_id,
                property=str(found.public_id),
                agent=str(visitor.public_id),
                scheduled_for=scheduled_for.isoformat(),
            )
        return visit

    async def cancel(self, actor: Actor, visit_id: uuid.UUID, *, reason: str) -> VerificationVisit:
        """Call off a booked visit; the property's status goes back to what it was before."""
        check(_reason_problems(reason))
        async with self._db.begin():
            visit = await self._visits.visit(visit_id, lock=True)
            if visit is None:
                raise NotFoundError
            if visit.status != VisitStatus.SCHEDULED:
                raise InvalidTransitionError(f"A {visit.status} visit can't be cancelled.")
            found = await self._catalog.property_by_id(visit.property_id, lock=True)
            found.verification_status = visit.status_before
            visit.status = VisitStatus.CANCELLED
            visit.cancelled_at = self._clock.now()
            visit.cancel_reason = reason.strip()
            await self._db.flush()
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.verification_cancelled",
                entity="verification_visit",
                entity_id=visit.public_id,
                reason=reason.strip(),
            )
        return visit

    async def submit(self, actor: Actor, visit_id: uuid.UUID, report: Report) -> VerificationVisit:
        """The agent's report. Only the agent the visit was booked for can send it; to anyone
        else the visit doesn't exist."""
        problems = report_problems(
            report.checklist, report.result, notes=report.notes, photos=len(report.photos)
        )
        problems += location_problems(report.position)
        if len(set(report.photos)) != len(report.photos):
            problems.append("a photo is listed twice")
        check(problems)
        now = self._clock.now()
        async with self._db.begin():
            visit = await self._visits.visit(visit_id, lock=True)
            if visit is None or visit.agent_id != actor.user_id:
                raise NotFoundError
            if visit.status != VisitStatus.SCHEDULED:
                raise InvalidTransitionError(f"A {visit.status} visit can't take a report.")
            photos = await self._photos(actor, report.photos)
            found = await self._catalog.property_by_id(visit.property_id, lock=True)
            exact, _ = await self._catalog.points(found.id)
            # The position first: the database checks a submitted visit has its whole report.
            await self._visits.set_position(visit, report.position)
            visit.status = VisitStatus.SUBMITTED
            visit.submitted_at = now
            visit.position_accuracy_m = round(report.accuracy_m)
            visit.distance_m = round(distance_m(report.position, exact))
            visit.checklist = checklist_to_json(report.checklist)
            visit.result = report.result
            visit.notes = report.notes.strip()
            await self._db.flush()
            await self._visits.add_photos(visit.id, photos)
            if report.move_pin and report.position != exact:
                display = moved(report.position, random_offset(self._rng))
                await self._catalog.set_points(found, report.position, display)
            outcome = status_after(report.result)
            found.verification_status = outcome
            await self._db.flush()
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.verification_submitted",
                entity="verification_visit",
                entity_id=visit.public_id,
                result=report.result.value,
                distance_m=visit.distance_m,
                pin_moved=report.move_pin,
            )
            await self._take_down_if_needed(actor, found, outcome)
        return visit

    async def suspend(self, actor: Actor, property_id: uuid.UUID, *, reason: str) -> Property:
        """Withdraw a verified property's verification: a complaint, an authorities' notice."""
        check(_reason_problems(reason))
        async with self._db.begin():
            found = await self._catalog.property(property_id, lock=True)
            if found is None:
                raise NotFoundError
            current = VerificationStatus(found.verification_status)
            if not can_suspend(current):
                raise InvalidTransitionError(f"A {current} property can't be suspended.")
            found.verification_status = VerificationStatus.SUSPENDED
            await self._db.flush()
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.verification_suspended",
                entity="property",
                entity_id=found.public_id,
                reason=reason.strip(),
            )
            await self._take_down_if_needed(actor, found, VerificationStatus.SUSPENDED)
        return found

    async def _photos(self, actor: Actor, photos: Sequence[uuid.UUID]) -> list[int]:
        """The report's photos, which must be the agent's own verification photos and ready."""
        refs = await self._media.by_public_id(set(photos))
        problems = []
        for photo in photos:
            ref = refs.get(photo)
            if ref is None or ref.uploaded_by != actor.user_id:
                problems.append(f"no such photo: {photo}")
            elif ref.purpose is not Purpose.VERIFICATION_PHOTO:
                problems.append(f"{photo} isn't a verification photo")
            elif ref.status is not AssetStatus.READY:
                problems.append(f"{photo} is {ref.status}")
        check(problems)
        return [refs[photo].id for photo in photos]

    async def _take_down_if_needed(
        self, actor: Actor, found: Property, verification: VerificationStatus
    ) -> None:
        """A live listing whose building failed its checks, or was suspended, is paused."""
        status = PropertyStatus(found.status)
        if keeps_listing_live(verification) or status is not PropertyStatus.PUBLISHED:
            return
        if not can_move(status, PropertyStatus.PAUSED):  # pragma: no cover - the state machine
            return
        found.status = PropertyStatus.PAUSED
        await self._db.flush()
        await staff_did(
            self._db,
            self._clock,
            actor,
            "catalog.property_status_changed",
            entity="property",
            entity_id=found.public_id,
            reason=f"verification {verification}",
            **{"from": status.value, "to": PropertyStatus.PAUSED.value},
        )


class VisitReader:
    """What staff see of visits: a field agent their own, ops and admins all of them."""

    def __init__(self, db: AsyncSession, *, buckets: Buckets, storage: ObjectStorage) -> None:
        self._db = db
        self._catalog = CatalogRepository(db)
        self._visits = VisitRepository(db)
        self._accounts = Accounts(db)
        self._geo = GeoLookup(db)
        # Report photos are private: the links are signed, for the people allowed to read.
        self._media = MediaLookup(db, buckets, storage=storage)

    async def field_agents(self) -> list[Account]:
        """Who a visit can be booked for: active accounts with the field agent role."""
        async with self._db.begin():
            return await self._accounts.with_role(Role.FIELD_AGENT)

    async def visit(self, visit_id: uuid.UUID, *, agent_id: int | None = None) -> VisitView:
        """One visit in full. With ``agent_id``, only if it was booked for that agent."""
        async with self._db.begin():
            visit = await self._visits.visit(visit_id)
            if visit is None or (agent_id is not None and visit.agent_id != agent_id):
                raise NotFoundError
            return (await self._views([visit]))[0]

    async def page(
        self,
        request: PageRequest,
        *,
        agent_id: int | None = None,
        status: VisitStatus | None = None,
    ) -> tuple[list[VisitView], uuid.UUID | None]:
        async with self._db.begin():
            rows = await self._visits.page(
                after=request.after, limit=request.limit, agent_id=agent_id, status=status
            )
            found, next_cursor = split_page(rows, request, cursor_of=lambda row: row.public_id)
            return await self._views(found), next_cursor

    async def of_property(
        self, property_id: uuid.UUID, request: PageRequest
    ) -> tuple[list[VisitView], uuid.UUID | None]:
        """A property's visits, newest first."""
        async with self._db.begin():
            found = await self._catalog.property(property_id)
            if found is None:
                raise NotFoundError
            rows = await self._visits.of_property(
                found.id, before=request.after, limit=request.limit
            )
            visits, next_cursor = split_page(rows, request, cursor_of=lambda row: row.public_id)
            return await self._views(visits), next_cursor

    async def _views(self, visits: Sequence[VerificationVisit]) -> list[VisitView]:
        """Views of ``visits`` in a fixed number of queries, however many there are."""
        if not visits:
            return []
        properties = await self._catalog.properties_by_id({visit.property_id for visit in visits})
        owners = await self._catalog.owners_by_id({row.owner_id for row in properties.values()})
        accounts = await self._accounts.many(
            {visit.agent_id for visit in visits} | {owner.user_id for owner in owners.values()}
        )
        localities = await self._geo.localities({row.locality_id for row in properties.values()})
        exact = await self._catalog.exact_points(properties.keys())
        positions = await self._visits.positions([visit.id for visit in visits])
        photos = await self._visits.photos_of([visit.id for visit in visits])
        media = await self._media.by_id({asset for ids in photos.values() for asset in ids})
        views = []
        for visit in visits:
            found = properties[visit.property_id]
            owner = owners[found.owner_id]
            owner_account = accounts.get(owner.user_id)
            views.append(
                VisitView(
                    visit=visit,
                    property=VisitProperty(
                        property=found,
                        locality=localities[found.locality_id],
                        exact=exact[found.id],
                        owner_business=owner.business_name,
                        owner_phone=None if owner_account is None else owner_account.phone_e164,
                    ),
                    agent=accounts.get(visit.agent_id),
                    position=positions.get(visit.id),
                    checklist=None
                    if visit.checklist is None
                    else checklist_from_json(visit.checklist),
                    photos=tuple(
                        media[asset] for asset in photos.get(visit.id, []) if asset in media
                    ),
                )
            )
        return views
