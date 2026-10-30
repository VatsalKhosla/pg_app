"""Queries on bookings and their events. Repositories never commit; services own transactions."""

from typing import TYPE_CHECKING

from sqlalchemy import func, select, update

from app.modules.booking.domain.state_machine import BookingStatus
from app.modules.booking.models import Booking, BookingEventRecord

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class BookingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def add(self, booking: Booking) -> None:
        self._db.add(booking)

    def record(self, entry: BookingEventRecord) -> None:
        self._db.add(entry)

    async def by_code(self, code: str) -> Booking | None:
        return await self._db.scalar(select(Booking).where(Booking.code == code))

    async def by_quote(self, quote_id: int) -> Booking | None:
        return await self._db.scalar(select(Booking).where(Booking.quote_id == quote_id))

    async def lock_holds_of(self, student_id: int) -> None:
        """Until the transaction ends, the student's other holds wait for this one, so two at
        once can't both slip under the limit."""
        await self._db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(f"holds:{student_id}", 0)))
        )

    async def active_holds(self, student_id: int, *, now: datetime) -> int:
        """The student's holds that haven't expired."""
        count = await self._db.scalar(
            select(func.count()).where(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.HELD,
                Booking.hold_expires_at > now,
            )
        )
        return count or 0

    async def stale_holds(self, bed_ids: Collection[int], *, now: datetime) -> list[Booking]:
        """The holds on these beds past their expiry, locked, oldest first."""
        if not bed_ids:
            return []
        rows = await self._db.scalars(
            select(Booking)
            .where(
                Booking.bed_id.in_(bed_ids),
                Booking.status == BookingStatus.HELD,
                Booking.hold_expires_at <= now,
            )
            .order_by(Booking.id)
            .with_for_update()
        )
        return list(rows)

    async def compare_and_set(
        self, booking: Booking, *, to: BookingStatus, values: Mapping[str, object]
    ) -> bool:
        """Moves the booking to ``to``, with ``values``, unless something changed it since it
        was read: the same status and the same version (ARCHITECTURE §7.2)."""
        moved = await self._db.scalar(
            update(Booking)
            .where(
                Booking.id == booking.id,
                Booking.status == booking.status,
                Booking.version == booking.version,
            )
            .values(status=to, version=Booking.version + 1, **values)
            .returning(Booking.id)
            .execution_options(synchronize_session=False)
        )
        if moved is None:
            return False
        await self._db.refresh(booking)
        return True
