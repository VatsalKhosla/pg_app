"""Queries on the policy tables. Repositories never commit; services own transactions."""

from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select

from app.modules.pricing.models import PolicyVersion, RentBand

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class PolicyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def lock(self, table: str) -> None:
        """Until the transaction ends, other changes to ``table`` wait, and then see this one."""
        await self._db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(f"pricing:{table}", 0)))
        )

    async def in_force[V: PolicyVersion](self, model: type[V], *, at: datetime) -> V | None:
        """The version in force at ``at``, if any."""
        return await self._db.scalar(
            select(model).where(
                model.effective_from <= at,
                or_(model.effective_to.is_(None), model.effective_to > at),
            )
        )

    async def history[V: PolicyVersion](self, model: type[V], *, limit: int) -> list[V]:
        """The latest versions, newest first."""
        rows = await self._db.scalars(
            select(model).order_by(model.effective_from.desc()).limit(limit)
        )
        return list(rows)

    def add(self, version: PolicyVersion) -> None:
        self._db.add(version)


class RentBandRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def in_force(self, locality_id: int, occupancy: str, *, at: datetime) -> RentBand | None:
        return await self._db.scalar(
            select(RentBand).where(
                RentBand.locality_id == locality_id,
                RentBand.occupancy == occupancy,
                RentBand.effective_from <= at,
                or_(RentBand.effective_to.is_(None), RentBand.effective_to > at),
            )
        )

    async def get(self, public_id: uuid.UUID, *, lock: bool = False) -> RentBand | None:
        query = select(RentBand).where(RentBand.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def listed(
        self, *, locality_id: int | None, at: datetime, ended: bool, limit: int
    ) -> list[RentBand]:
        """Bands in force at ``at`` (with ``ended``, past ones too), newest first."""
        query = select(RentBand).order_by(RentBand.effective_from.desc()).limit(limit)
        if locality_id is not None:
            query = query.where(RentBand.locality_id == locality_id)
        if not ended:
            query = query.where(
                RentBand.effective_from <= at,
                or_(RentBand.effective_to.is_(None), RentBand.effective_to > at),
            )
        return list(await self._db.scalars(query))
