"""Queries on bookings, their events and their disputes. Repositories never commit; services own
transactions."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from sqlalchemy import ColumnElement, and_, func, or_, select, update

from app.modules.booking.domain.board import QUEUES, UNCONFIRMED_SLA
from app.modules.booking.domain.state_machine import BookingEvent, BookingStatus
from app.modules.booking.models import Booking, BookingEventRecord, Dispute, DisputePhoto

# Confirmed, and moved in or finished since: the bookings that show the owner's contact (rule 11).
CONFIRMED_ONWARDS: Final = (
    BookingStatus.CONFIRMED,
    BookingStatus.CHECKED_IN,
    BookingStatus.DISPUTED,
    BookingStatus.ACTIVE,
    BookingStatus.COMPLETED,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Mapping, Sequence
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.booking.domain.disputes import DisputeStatus


@dataclass(frozen=True, slots=True)
class BoardFilter:
    """Which bookings the board shows (step 5.10, ADR 0054)."""

    status: BookingStatus | None = None
    channel: str | None = None
    # Only those needing a person at this moment: (now, today in India).
    attention_at: tuple[datetime, date] | None = None
    # A search found this booking, this student's or these PGs'.
    code: str | None = None
    student_id: int | None = None
    property_ids: Collection[int] | None = None


@dataclass(frozen=True, slots=True)
class BoardCounts:
    by_status: dict[BookingStatus, int]
    unconfirmed_late: int
    disputes: int
    move_ins: int


def _unconfirmed_late(now: datetime) -> ColumnElement[bool]:
    return and_(
        Booking.status == BookingStatus.TOKEN_SECURED,
        Booking.token_secured_at <= now - UNCONFIRMED_SLA,
    )


def _move_in_due(today: date) -> ColumnElement[bool]:
    return and_(Booking.status == BookingStatus.CONFIRMED, Booking.move_in <= today)


class BookingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def add(self, booking: Booking) -> None:
        self._db.add(booking)

    def record(self, entry: BookingEventRecord) -> None:
        self._db.add(entry)

    async def by_code(self, code: str, *, lock: bool = False) -> Booking | None:
        query = select(Booking).where(Booking.code == code)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def by_public_id(self, public_id: uuid.UUID, *, lock: bool = False) -> Booking | None:
        query = select(Booking).where(Booking.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def by_id(self, booking_id: int, *, lock: bool = False) -> Booking | None:
        query = select(Booking).where(Booking.id == booking_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def by_ids(self, booking_ids: Collection[int]) -> dict[int, Booking]:
        if not booking_ids:
            return {}
        rows = await self._db.scalars(select(Booking).where(Booking.id.in_(booking_ids)))
        return {row.id: row for row in rows}

    async def holds_over(self, now: datetime, *, limit: int) -> list[Booking]:
        """Holds past their expiry, locked, the longest over first; ones another transaction
        holds are left to it, such as a new hold on the same beds expiring them itself."""
        rows = await self._db.scalars(
            select(Booking)
            .where(Booking.status == BookingStatus.HELD, Booking.hold_expires_at <= now)
            .order_by(Booking.hold_expires_at, Booking.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(rows)

    async def not_moved_in(self, today: date, *, limit: int) -> list[Booking]:
        """Confirmed bookings whose move-in day has gone, locked, the longest gone first. Each
        booking's own terms say how long it waits for a no-show; the state machine decides."""
        rows = await self._db.scalars(
            select(Booking)
            .where(Booking.status == BookingStatus.CONFIRMED, Booking.move_in < today)
            .order_by(Booking.move_in, Booking.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(rows)

    async def windows_over(self, now: datetime, *, limit: int) -> list[Booking]:
        """Checked-in bookings whose 24 hours to check the room are over, locked, the earliest
        first; ones another run holds are left to it."""
        rows = await self._db.scalars(
            select(Booking)
            .where(Booking.status == BookingStatus.CHECKED_IN, Booking.check_window_ends_at <= now)
            .order_by(Booking.check_window_ends_at, Booking.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(rows)

    async def unconfirmed_past(self, now: datetime, *, limit: int) -> list[Booking]:
        """Bookings with the token in whose owner hasn't confirmed by their deadline, locked,
        the most overdue first; ones another run holds are left to it."""
        rows = await self._db.scalars(
            select(Booking)
            .where(Booking.status == BookingStatus.TOKEN_SECURED, Booking.confirm_by <= now)
            .order_by(Booking.confirm_by, Booking.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(rows)

    async def by_quote(self, quote_id: int) -> Booking | None:
        return await self._db.scalar(select(Booking).where(Booking.quote_id == quote_id))

    async def of_student(self, student_id: int) -> list[Booking]:
        """Every booking the student made, newest first."""
        rows = await self._db.scalars(
            select(Booking)
            .where(Booking.student_id == student_id)
            .order_by(Booking.created_at.desc(), Booking.id.desc())
        )
        return list(rows)

    async def events_of(self, booking_ids: Collection[int]) -> dict[int, list[BookingEventRecord]]:
        """Each booking's changes, oldest first."""
        if not booking_ids:
            return {}
        rows = await self._db.scalars(
            select(BookingEventRecord)
            .where(BookingEventRecord.booking_id.in_(booking_ids))
            .order_by(BookingEventRecord.id)
        )
        found: dict[int, list[BookingEventRecord]] = {}
        for row in rows:
            found.setdefault(row.booking_id, []).append(row)
        return found

    async def confirmed_at(self, student_id: int, property_id: int) -> bool:
        """Whether the student has a booking at the PG that its owner confirmed."""
        found = await self._db.scalar(
            select(Booking.id)
            .where(
                Booking.student_id == student_id,
                Booking.property_id == property_id,
                Booking.status.in_(CONFIRMED_ONWARDS),
            )
            .limit(1)
        )
        return found is not None

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

    async def board(
        self, found: BoardFilter, *, after: uuid.UUID | None, limit: int
    ) -> list[Booking]:
        """The board's bookings, ``limit + 1`` of them (the extra one says there's more). Ones
        still moving come oldest first, as a queue; the others newest first."""
        query = select(Booking)
        if found.status is not None:
            query = query.where(Booking.status == found.status)
        if found.channel is not None:
            query = query.where(Booking.channel == found.channel)
        if found.attention_at is not None:
            now, today = found.attention_at
            query = query.where(
                or_(
                    _unconfirmed_late(now),
                    Booking.status == BookingStatus.DISPUTED,
                    _move_in_due(today),
                )
            )
        if found.code is not None:
            query = query.where(Booking.code == found.code)
        if found.student_id is not None:
            query = query.where(Booking.student_id == found.student_id)
        if found.property_ids is not None:
            query = query.where(Booking.property_id.in_(found.property_ids))
        oldest_first = found.attention_at is not None or found.status in QUEUES
        if after is not None:
            query = query.where(
                Booking.public_id > after if oldest_first else Booking.public_id < after
            )
        order = Booking.public_id if oldest_first else Booking.public_id.desc()
        return list(await self._db.scalars(query.order_by(order).limit(limit + 1)))

    async def board_counts(self, *, now: datetime, today: date) -> BoardCounts:
        rows = await self._db.execute(
            select(Booking.status, func.count().label("bookings")).group_by(Booking.status)
        )
        waiting = (
            await self._db.execute(
                select(
                    func.count().filter(_unconfirmed_late(now)).label("unconfirmed_late"),
                    func.count().filter(Booking.status == BookingStatus.DISPUTED).label("disputes"),
                    func.count().filter(_move_in_due(today)).label("move_ins"),
                )
            )
        ).one()
        return BoardCounts(
            by_status={BookingStatus(row.status): row.bookings for row in rows},
            unconfirmed_late=waiting.unconfirmed_late,
            disputes=waiting.disputes,
            move_ins=waiting.move_ins,
        )

    async def owner_cancellations(self, owner_id: int) -> int:
        """How many bookings this owner has cancelled after taking them: the state machine's
        FlagOwner, as the rows record it."""
        count = await self._db.scalar(
            select(func.count()).where(
                Booking.owner_id == owner_id,
                Booking.cancellation_kind == BookingEvent.OWNER_CANCEL,
            )
        )
        return count or 0

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


class DisputeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, dispute: Dispute, photos: Sequence[int]) -> None:
        """The dispute, with its photos (media asset ids) in the student's order."""
        self._db.add(dispute)
        await self._db.flush()
        self._db.add_all(
            DisputePhoto(dispute_id=dispute.id, media_asset_id=media_id, position=position)
            for position, media_id in enumerate(photos)
        )
        await self._db.flush()

    async def by_public_id(self, public_id: uuid.UUID, *, lock: bool = False) -> Dispute | None:
        query = select(Dispute).where(Dispute.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def of_bookings(self, booking_ids: Collection[int]) -> dict[int, Dispute]:
        if not booking_ids:
            return {}
        rows = await self._db.scalars(select(Dispute).where(Dispute.booking_id.in_(booking_ids)))
        return {row.booking_id: row for row in rows}

    async def page(
        self, *, status: DisputeStatus | None, after: uuid.UUID | None, limit: int
    ) -> list[Dispute]:
        """Disputes oldest first, of one status if asked, ``limit + 1`` of them (the extra one
        says there's more): a queue, worked from its front."""
        query = select(Dispute)
        if status is not None:
            query = query.where(Dispute.status == status)
        if after is not None:
            query = query.where(Dispute.public_id > after)
        rows = await self._db.scalars(query.order_by(Dispute.public_id).limit(limit + 1))
        return list(rows)

    async def photo_counts(self, dispute_ids: Collection[int]) -> dict[int, int]:
        """How many photos each dispute has; one with none is left out."""
        if not dispute_ids:
            return {}
        rows = await self._db.execute(
            select(DisputePhoto.dispute_id, func.count().label("photos"))
            .where(DisputePhoto.dispute_id.in_(dispute_ids))
            .group_by(DisputePhoto.dispute_id)
        )
        return {row.dispute_id: row.photos for row in rows}

    async def photos_of(self, dispute_id: int) -> list[int]:
        """The dispute's photos, as media asset ids, in the student's order."""
        rows = await self._db.scalars(
            select(DisputePhoto.media_asset_id)
            .where(DisputePhoto.dispute_id == dispute_id)
            .order_by(DisputePhoto.position)
        )
        return list(rows)
