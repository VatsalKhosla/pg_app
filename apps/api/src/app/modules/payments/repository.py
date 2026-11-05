"""The payments module's queries. It never commits: services own the transaction."""

from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.modules.payments.models import Payment

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection

    from sqlalchemy.ext.asyncio import AsyncSession


class PaymentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def by_public_id(self, public_id: uuid.UUID, *, lock: bool = False) -> Payment | None:
        query = select(Payment).where(Payment.public_id == public_id)
        # A locked read is about the row as it is now: not the copy this session read before the
        # lock, which is what it would otherwise be given back.
        locked = query.with_for_update().execution_options(populate_existing=True)
        return await self._db.scalar(locked if lock else query)

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
