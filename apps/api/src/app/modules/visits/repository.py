"""Reads and writes of the visits module's own table."""

from typing import TYPE_CHECKING

from sqlalchemy import func, select, update

from app.core import postgis
from app.core.geometry import Point
from app.modules.visits.domain.visits import ENTITLING, OPEN, StudentVisitStatus
from app.modules.visits.models import Visit

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class VisitRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, visit: Visit) -> Visit:
        self._db.add(visit)
        await self._db.flush()
        return visit

    async def get(self, public_id: uuid.UUID, *, lock: bool = False) -> Visit | None:
        query = select(Visit).where(Visit.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def lock_student(self, student_id: int) -> None:
        """Until the transaction ends, this student's other requests wait: two at once can't
        both pass the limit on open visits."""
        await self._db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(f"visits:{student_id}", 0)))
        )

    async def open_count(self, student_id: int) -> int:
        return (
            await self._db.scalar(
                select(func.count())
                .select_from(Visit)
                .where(Visit.student_id == student_id, Visit.status.in_(OPEN))
            )
            or 0
        )

    async def open_to(self, student_id: int, property_id: int) -> Visit | None:
        return await self._db.scalar(
            select(Visit).where(
                Visit.student_id == student_id,
                Visit.property_id == property_id,
                Visit.status.in_(OPEN),
            )
        )

    async def of_student(self, student_id: int, *, limit: int) -> list[Visit]:
        """A student's visits, newest first."""
        found = await self._db.scalars(
            select(Visit)
            .where(Visit.student_id == student_id)
            .order_by(Visit.public_id.desc())
            .limit(limit)
        )
        return list(found)

    async def page(
        self, *, status: StudentVisitStatus | None, before: uuid.UUID | None, limit: int
    ) -> list[Visit]:
        """Every visit, newest first, ``limit + 1`` of them (the extra one says there's more)."""
        query = select(Visit)
        if status is not None:
            query = query.where(Visit.status == status)
        if before is not None:
            query = query.where(Visit.public_id < before)
        found = await self._db.scalars(query.order_by(Visit.public_id.desc()).limit(limit + 1))
        return list(found)

    async def of_agent(self, agent_id: int, *, since: datetime, limit: int) -> list[Visit]:
        """An agent's booked visits from ``since``, soonest first."""
        found = await self._db.scalars(
            select(Visit)
            .where(
                Visit.agent_id == agent_id,
                Visit.scheduled_at >= since,
                Visit.status != StudentVisitStatus.CANCELLED,
            )
            .order_by(Visit.scheduled_at, Visit.public_id)
            .limit(limit)
        )
        return list(found)

    async def entitled(self, student_id: int, property_id: int) -> bool:
        found = await self._db.scalar(
            select(Visit.id)
            .where(
                Visit.student_id == student_id,
                Visit.property_id == property_id,
                Visit.status.in_(ENTITLING),
            )
            .limit(1)
        )
        return found is not None

    async def check_in(
        self, visit: Visit, *, at: datetime, position: Point, accuracy_m: int, distance_m: int
    ) -> None:
        """The visit log in one statement: the database checks it's all there together."""
        await self._db.execute(
            update(Visit)
            .where(Visit.id == visit.id)
            .values(
                checked_in_at=at,
                check_in_position=postgis.point_wkt(position),
                check_in_accuracy_m=accuracy_m,
                check_in_distance_m=distance_m,
            )
            .execution_options(synchronize_session=False)
        )
        await self._db.refresh(visit)

    async def positions(self, ids: Collection[int]) -> dict[int, Point]:
        """Where agents checked in, by visit id."""
        if not ids:
            return {}
        rows = await self._db.execute(
            select(
                Visit.id,
                postgis.lat(Visit.check_in_position),
                postgis.lng(Visit.check_in_position),
            ).where(Visit.id.in_(ids), Visit.check_in_position.is_not(None))
        )
        return {visit_id: Point(lat=lat, lng=lng) for visit_id, lat, lng in rows}
