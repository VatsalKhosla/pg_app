"""The payments module's queries. It never commits: services own the transaction."""

from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.modules.payments.domain.payments import PaymentPurpose, PaymentStatus
from app.modules.payments.models import Payment, PaymentEvent, Refund

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.payments.domain.refunds import RefundKind, RefundStatus


class PaymentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def by_public_id(self, public_id: uuid.UUID, *, lock: bool = False) -> Payment | None:
        query = select(Payment).where(Payment.public_id == public_id)
        # A locked read is about the row as it is now: not the copy this session read before the
        # lock, which is what it would otherwise be given back.
        locked = query.with_for_update().execution_options(populate_existing=True)
        return await self._db.scalar(locked if lock else query)

    async def by_id(self, payment_id: int, *, lock: bool = False) -> Payment:
        query = select(Payment).where(Payment.id == payment_id)
        locked = query.with_for_update().execution_options(populate_existing=True)
        return (await self._db.scalars(locked if lock else query)).one()

    async def by_ids(self, payment_ids: Collection[int]) -> dict[int, Payment]:
        if not payment_ids:
            return {}
        rows = await self._db.scalars(select(Payment).where(Payment.id.in_(payment_ids)))
        return {row.id: row for row in rows}

    async def by_provider_payment(self, provider: str, payment_id: str) -> Payment | None:
        """The payment the gateway knows by this id, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(Payment.provider == provider, Payment.provider_payment_id == payment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def captured_token_of(self, booking_id: int) -> Payment | None:
        """The booking's token that came in, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(
                Payment.booking_id == booking_id,
                Payment.purpose == PaymentPurpose.TOKEN,
                Payment.status == PaymentStatus.CAPTURED,
            )
            .order_by(Payment.id.desc())
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def by_order(self, provider: str, order_id: str) -> Payment | None:
        """The payment for this order at this gateway, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(Payment.provider == provider, Payment.provider_order_id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def by_key(self, key: str) -> Payment | None:
        return await self._db.scalar(select(Payment).where(Payment.idempotency_key == key))

    async def add_once(
        self,
        *,
        booking_id: int,
        purpose: str,
        mode: str,
        provider: str,
        key: str,
        amount_paise: int,
    ) -> Payment:
        """The payment with this key, added if there isn't one yet. Two requests at once get the
        same row."""
        await self._db.execute(
            insert(Payment)
            .values(
                booking_id=booking_id,
                purpose=purpose,
                mode=mode,
                provider=provider,
                idempotency_key=key,
                amount_paise=amount_paise,
            )
            .on_conflict_do_nothing(index_elements=[Payment.idempotency_key])
        )
        found = await self.by_key(key)
        assert found is not None  # noqa: S101 - just added, or there already
        return found

    async def set_order_once(self, public_id: uuid.UUID, order_id: str) -> bool:
        """Keeps the first order given to this payment, should two requests ask at once: whether
        this was it."""
        changed = await self._db.scalar(
            update(Payment)
            .where(Payment.public_id == public_id, Payment.provider_order_id.is_(None))
            .values(provider_order_id=order_id)
            .returning(Payment.id)
        )
        return changed is not None

    async def order_id_of(self, public_id: uuid.UUID) -> str | None:
        """The order as saved now, whatever this session read earlier."""
        return await self._db.scalar(
            select(Payment.provider_order_id).where(Payment.public_id == public_id)
        )

    async def of_bookings(self, booking_ids: Collection[int]) -> list[Payment]:
        if not booking_ids:
            return []
        rows = await self._db.scalars(
            select(Payment).where(Payment.booking_id.in_(booking_ids)).order_by(Payment.id)
        )
        return list(rows)

    async def add_event_once(
        self,
        *,
        provider: str,
        event_id: str,
        kind: str,
        payload: dict[str, object],
        received_at: datetime,
    ) -> int | None:
        """The new event's id; None if this event was stored before."""
        return await self._db.scalar(
            insert(PaymentEvent)
            .values(
                provider=provider,
                provider_event_id=event_id,
                event_type=kind,
                payload=payload,
                received_at=received_at,
            )
            .on_conflict_do_nothing(constraint="uq_payment_events_provider_event")
            .returning(PaymentEvent.id)
        )

    async def event(self, event_id: int) -> PaymentEvent | None:
        """The event, locked, as it is now."""
        return await self._db.scalar(
            select(PaymentEvent)
            .where(PaymentEvent.id == event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def add_refund_once(
        self,
        *,
        payment_id: int,
        kind: RefundKind,
        status: RefundStatus,
        amount_paise: int,
        reason: str,
        key: str,
        requested_at: datetime,
        requested_by: int | None,
    ) -> Refund | None:
        """The new refund; None if this key has one already."""
        new = await self._db.scalar(
            insert(Refund)
            .values(
                payment_id=payment_id,
                kind=kind,
                status=status,
                amount_paise=amount_paise,
                reason=reason,
                idempotency_key=key,
                requested_at=requested_at,
                requested_by=requested_by,
            )
            .on_conflict_do_nothing(index_elements=[Refund.idempotency_key])
            .returning(Refund.id)
        )
        if new is None:
            return None
        return await self._db.scalar(select(Refund).where(Refund.id == new))

    async def refund_by_key(self, key: str) -> Refund | None:
        """The refund with this key, locked, as it is now."""
        return await self._db.scalar(
            select(Refund)
            .where(Refund.idempotency_key == key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def refund_by_public_id(
        self, public_id: uuid.UUID, *, lock: bool = False
    ) -> Refund | None:
        query = select(Refund).where(Refund.public_id == public_id)
        locked = query.with_for_update().execution_options(populate_existing=True)
        return await self._db.scalar(locked if lock else query)

    async def refund_by_provider_id(self, provider_refund_id: str) -> Refund | None:
        """The refund the gateway knows by this id, locked, as it is now."""
        return await self._db.scalar(
            select(Refund)
            .where(Refund.provider_refund_id == provider_refund_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def refunds_of(self, payment_ids: Collection[int]) -> dict[int, list[Refund]]:
        """Each payment's refunds, oldest first; a payment with none is left out."""
        if not payment_ids:
            return {}
        rows = await self._db.scalars(
            select(Refund)
            .where(Refund.payment_id.in_(payment_ids))
            .order_by(Refund.id)
            .execution_options(populate_existing=True)
        )
        found: dict[int, list[Refund]] = {}
        for row in rows:
            found.setdefault(row.payment_id, []).append(row)
        return found

    async def refund_page(
        self, *, status: RefundStatus | None, after: uuid.UUID | None, limit: int
    ) -> list[Refund]:
        """Refunds oldest first, of one status if asked, ``limit + 1`` of them (the extra says
        there's more): a queue, worked from its front."""
        query = select(Refund)
        if status is not None:
            query = query.where(Refund.status == status)
        if after is not None:
            query = query.where(Refund.public_id > after)
        rows = await self._db.scalars(query.order_by(Refund.public_id).limit(limit + 1))
        return list(rows)
