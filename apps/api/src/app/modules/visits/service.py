"""Visits' use cases (ARCHITECTURE §11; step 3.7, ADR 0033); each method is one transaction.

A student asks to visit a PG the public can see, offering up to three times. Ops book one of them
(or another) with a field agent, which texts the student the time and the address and queues
reminders for the day before and two hours before. The agent checks in at the building, the
visit log, then records how it went. Students cancel their own visits; ops cancel any.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from app.config import BRAND_NAME
from app.core import audit
from app.core.actor import Role
from app.core.calendar import INDIA
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.flags import Flag
from app.core.geometry import NCR_BOUNDS, distance_m
from app.core.outbox import enqueue
from app.modules.catalog.service import CatalogLookup, VisitPlace
from app.modules.identity.service import Account, Accounts
from app.modules.visits.domain.visits import (
    MAX_OPEN_VISITS,
    CancelledBy,
    Outcome,
    StudentVisitStatus,
    can_move,
    may_check_in,
    reminders,
    schedule_problems,
    start_problems,
    status_after,
)
from app.modules.visits.errors import (
    CheckInRequiredError,
    CheckInTooEarlyError,
    VisitExistsError,
    VisitInvalidError,
    VisitLimitReachedError,
)
from app.modules.visits.models import Visit
from app.modules.visits.repository import VisitRepository
from app.modules.visits.texts import CANCELLED, REMINDER, SCHEDULED

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.flags import FlagReader
    from app.core.geometry import Point

TEXT: Final = "visits.text"
# A student's own list, and an agent's: plenty for a season.
LIST_LIMIT: Final = 100
# An agent's list starts with the visits of the day before, which they may still be finishing.
AGENT_LOOKBACK: Final = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class VisitView:
    visit: Visit
    place: VisitPlace
    student: Account
    agent: Account | None
    # Where the agent checked in.
    position: Point | None


def when(moment: datetime) -> str:
    """A visit's time as a text says it, in India: "Sat 2 Nov, 11:30 am"."""
    local = moment.astimezone(INDIA)
    hour = local.hour % 12 or 12
    half = "am" if local.hour < 12 else "pm"
    return f"{local:%a} {local.day} {local:%b}, {hour}:{local:%M} {half}"


class VisitService:
    def __init__(self, db: AsyncSession, clock: Clock, *, flags: FlagReader) -> None:
        self._db = db
        self._clock = clock
        self._flags = flags
        self._visits = VisitRepository(db)
        self._catalog = CatalogLookup(db)
        self._accounts = Accounts(db)

    # Students.

    async def request(self, actor: Actor, slug: str, starts: Sequence[datetime]) -> VisitView:
        now = self._clock.now()
        if problems := start_problems(starts, now=now):
            raise VisitInvalidError(problems)
        verified_only = await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        async with self._db.begin():
            place = await self._catalog.visit_place(slug, verified_only=verified_only)
            if place is None or not place.public:
                raise NotFoundError
            await self._visits.lock_student(actor.user_id)
            if await self._visits.open_to(actor.user_id, place.id) is not None:
                raise VisitExistsError
            if await self._visits.open_count(actor.user_id) >= MAX_OPEN_VISITS:
                msg = f"You can have {MAX_OPEN_VISITS} visits open at once: cancel one first."
                raise VisitLimitReachedError(msg)
            visit = await self._visits.add(
                Visit(
                    property_id=place.id,
                    student_id=actor.user_id,
                    status=StudentVisitStatus.REQUESTED,
                    preferred_starts=sorted(starts),
                    requested_at=now,
                )
            )
            await self._audit(
                actor,
                "visits.requested",
                visit,
                starts=[start.isoformat() for start in sorted(starts)],
            )
            return (await self._views([visit]))[0]

    async def mine(self, actor: Actor) -> list[VisitView]:
        async with self._db.begin():
            return await self._views(await self._visits.of_student(actor.user_id, limit=LIST_LIMIT))

    async def cancel_mine(self, actor: Actor, visit_id: uuid.UUID) -> VisitView:
        async with self._db.begin():
            visit = await self._visits.get(visit_id, lock=True)
            if visit is None or visit.student_id != actor.user_id:
                raise NotFoundError
            self._cancel(visit, CancelledBy.STUDENT, reason="")
            await self._audit(actor, "visits.cancelled", visit, by=CancelledBy.STUDENT)
            return (await self._views([visit]))[0]

    # Ops.

    async def page(
        self, *, status: StudentVisitStatus | None, cursor: uuid.UUID | None, limit: int
    ) -> tuple[list[VisitView], uuid.UUID | None]:
        async with self._db.begin():
            found = await self._visits.page(status=status, before=cursor, limit=limit)
            views = await self._views(found[:limit])
        return views, (found[limit - 1].public_id if len(found) > limit else None)

    async def get(self, visit_id: uuid.UUID) -> VisitView:
        async with self._db.begin():
            visit = await self._visits.get(visit_id)
            if visit is None:
                raise NotFoundError
            return (await self._views([visit]))[0]

    async def schedule(
        self, actor: Actor, visit_id: uuid.UUID, *, at: datetime, agent: uuid.UUID
    ) -> VisitView:
        """Book the visit at ``at`` with ``agent``, or change either: the student is texted the
        time and the address, and reminded the day before and two hours before."""
        now = self._clock.now()
        if problems := schedule_problems(at, now=now):
            raise VisitInvalidError(problems)
        async with self._db.begin():
            visit = await self._visits.get(visit_id, lock=True)
            if visit is None:
                raise NotFoundError
            found = await self._accounts.active_with_role(agent, Role.FIELD_AGENT)
            if found is None:
                raise VisitInvalidError(["no field agent has that id"])
            self._move(visit, StudentVisitStatus.SCHEDULED)
            if visit.checked_in_at is not None:
                raise InvalidTransitionError("The agent has checked in: record how it went.")
            new_time = visit.scheduled_at != at
            visit.scheduled_at, visit.agent_id, visit.scheduled_by = at, found.id, actor.user_id
            await self._audit(
                actor, "visits.scheduled", visit, at=at.isoformat(), agent=str(found.public_id)
            )
            if new_time:
                await self._text(visit, SCHEDULED, name="scheduled", run_at=now)
                for name, run_at in reminders(at, now=now):
                    await self._text(visit, REMINDER, name=name, run_at=run_at)
            return (await self._views([visit]))[0]

    async def cancel(self, actor: Actor, visit_id: uuid.UUID, *, reason: str) -> VisitView:
        async with self._db.begin():
            visit = await self._visits.get(visit_id, lock=True)
            if visit is None:
                raise NotFoundError
            booked = visit.status == StudentVisitStatus.SCHEDULED
            self._cancel(visit, CancelledBy.OPS, reason=reason)
            await self._audit(actor, "visits.cancelled", visit, by=CancelledBy.OPS, reason=reason)
            if booked:
                await self._text(visit, CANCELLED, name="cancelled", run_at=self._clock.now())
            return (await self._views([visit]))[0]

    # Field agents.

    async def assigned(self, actor: Actor) -> list[VisitView]:
        since = self._clock.now() - AGENT_LOOKBACK
        async with self._db.begin():
            return await self._views(
                await self._visits.of_agent(actor.user_id, since=since, limit=LIST_LIMIT)
            )

    async def assigned_one(self, actor: Actor, visit_id: uuid.UUID) -> VisitView:
        async with self._db.begin():
            return (await self._views([await self._own(actor, visit_id, lock=False)]))[0]

    async def check_in(
        self, actor: Actor, visit_id: uuid.UUID, *, position: Point, accuracy_m: int
    ) -> VisitView:
        """The visit log: the time (the server's clock) and where the agent's phone says they
        are, with how far that is from the building."""
        now = self._clock.now()
        async with self._db.begin():
            visit = await self._own(actor, visit_id, lock=True)
            if visit.status != StudentVisitStatus.SCHEDULED or visit.checked_in_at is not None:
                raise InvalidTransitionError("Only a booked visit not yet checked in can be.")
            assert visit.scheduled_at is not None  # noqa: S101 - scheduled visits have one
            if not may_check_in(visit.scheduled_at, now=now):
                raise CheckInTooEarlyError
            if not NCR_BOUNDS.contains(position):
                raise VisitInvalidError(["that position is outside Delhi NCR"])
            place = (await self._catalog.visit_places([visit.property_id], verified_only=False))[
                visit.property_id
            ]
            metres = round(distance_m(position, place.exact))
            await self._visits.check_in(
                visit, at=now, position=position, accuracy_m=accuracy_m, distance_m=metres
            )
            await self._audit(
                actor, "visits.checked_in", visit, accuracy_m=accuracy_m, distance_m=metres
            )
            return (await self._views([visit]))[0]

    async def finish(
        self, actor: Actor, visit_id: uuid.UUID, *, outcome: Outcome, note: str
    ) -> VisitView:
        async with self._db.begin():
            visit = await self._own(actor, visit_id, lock=True)
            if visit.status == StudentVisitStatus.SCHEDULED and visit.checked_in_at is None:
                raise CheckInRequiredError
            self._move(visit, status_after(outcome))
            visit.outcome, visit.outcome_note = outcome, note
            visit.finished_at = self._clock.now()
            await self._audit(actor, "visits.finished", visit, outcome=outcome)
            return (await self._views([visit]))[0]

    # Shared.

    async def _own(self, actor: Actor, visit_id: uuid.UUID, *, lock: bool) -> Visit:
        """The agent's own visit; anyone else's is a 404."""
        visit = await self._visits.get(visit_id, lock=lock)
        if visit is None or visit.agent_id != actor.user_id:
            raise NotFoundError
        return visit

    @staticmethod
    def _move(visit: Visit, to: StudentVisitStatus) -> None:
        if not can_move(StudentVisitStatus(visit.status), to):
            msg = f"A {visit.status.replace('_', ' ')} visit can't become {to.replace('_', ' ')}."
            raise InvalidTransitionError(msg)
        visit.status = to

    def _cancel(self, visit: Visit, by: CancelledBy, *, reason: str) -> None:
        self._move(visit, StudentVisitStatus.CANCELLED)
        visit.cancelled_at, visit.cancelled_by, visit.cancel_reason = (
            self._clock.now(),
            by,
            reason,
        )

    async def _text(self, visit: Visit, template: str, *, name: str, run_at: datetime) -> None:
        """A text to the student, for the visit's time now: one per time, ever."""
        assert visit.scheduled_at is not None  # noqa: S101 - texts are about a booked time
        at = visit.scheduled_at.isoformat()
        await enqueue(
            self._db,
            TEXT,
            {"visit": str(visit.public_id), "template": template, "at": at},
            clock=self._clock,
            run_at=run_at,
            dedupe_key=f"{TEXT}:{visit.public_id}:{name}:{at}",
        )

    async def _audit(self, actor: Actor, action: str, visit: Visit, **details: object) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.Actor("staff" if actor.is_staff else "user", actor.user_id),
            action=action,
            entity_type="visit",
            entity_id=str(visit.public_id),
            details=details,
        )

    async def _views(self, visits: Sequence[Visit]) -> list[VisitView]:
        """The visits with their PGs, people and positions: four queries, however many."""
        places = await self._catalog.visit_places(
            {visit.property_id for visit in visits}, verified_only=False
        )
        people = await self._accounts.many(
            {visit.student_id for visit in visits}
            | {visit.agent_id for visit in visits if visit.agent_id is not None}
        )
        positions = await self._visits.positions(
            [visit.id for visit in visits if visit.checked_in_at is not None]
        )
        return [
            VisitView(
                visit=visit,
                place=places[visit.property_id],
                student=people[visit.student_id],
                agent=None if visit.agent_id is None else people[visit.agent_id],
                position=positions.get(visit.id),
            )
            for visit in visits
        ]


class VisitTexts:
    """What a queued text says, when the job comes to send it; nothing when the visit has moved
    on (cancelled, booked for another time, or done). Inside the job's transaction."""

    def __init__(self, db: AsyncSession) -> None:
        self._visits = VisitRepository(db)
        self._catalog = CatalogLookup(db)
        self._accounts = Accounts(db)

    async def message(
        self, visit_id: uuid.UUID, template: str, at: str
    ) -> tuple[str, dict[str, str]] | None:
        visit = await self._visits.get(visit_id)
        if visit is None or visit.scheduled_at != datetime.fromisoformat(at):
            return None
        wanted = (
            StudentVisitStatus.CANCELLED if template == CANCELLED else StudentVisitStatus.SCHEDULED
        )
        if visit.status != wanted:
            return None
        place = (await self._catalog.visit_places([visit.property_id], verified_only=False))[
            visit.property_id
        ]
        student = (await self._accounts.many([visit.student_id]))[visit.student_id]
        values = {"brand": BRAND_NAME, "pg": place.name, "when": when(visit.scheduled_at)}
        if template != CANCELLED:
            values["address"] = f"{place.address_line}, {place.locality}"
        return student.phone_e164, values
