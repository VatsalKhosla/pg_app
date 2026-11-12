"""Reading and writing invoices (step 6.5, ADR 0061). Never commits: the caller's transaction
does."""

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.calendar import INDIA_ZONE
from app.modules.invoices.models import InvoiceSequence, OwnerInvoice

if TYPE_CHECKING:
    import uuid
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class InvoiceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def next_serial(self, financial_year: str) -> int:
        """The year's next serial. Its row stays locked until the transaction ends."""
        taken = await self._db.execute(
            insert(InvoiceSequence)
            .values(financial_year=financial_year, last_serial=1)
            .on_conflict_do_update(
                index_elements=[InvoiceSequence.financial_year],
                set_={"last_serial": InvoiceSequence.last_serial + 1, "updated_at": func.now()},
            )
            .returning(InvoiceSequence.last_serial)
        )
        return int(taken.scalar_one())

    async def add(self, invoice: OwnerInvoice) -> None:
        self._db.add(invoice)
        await self._db.flush()

    async def by_booking(self, booking_id: int) -> OwnerInvoice | None:
        return await self._db.scalar(
            select(OwnerInvoice).where(OwnerInvoice.booking_id == booking_id)
        )

    async def by_public_id(
        self, public_id: uuid.UUID, *, lock: bool = False
    ) -> OwnerInvoice | None:
        query = select(OwnerInvoice).where(OwnerInvoice.public_id == public_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return await self._db.scalar(query)

    async def by_id(self, invoice_id: int, *, lock: bool = False) -> OwnerInvoice:
        query = select(OwnerInvoice).where(OwnerInvoice.id == invoice_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        found = await self._db.scalar(query)
        assert found is not None  # noqa: S101 - asked for by a row that refers to it
        return found

    async def page(
        self,
        *,
        owner_id: int | None,
        status: str | None,
        booking_code: str | None,
        after: uuid.UUID | None,
        limit: int,
    ) -> list[OwnerInvoice]:
        """Newest first, ``limit + 1`` of them (the extra says there's more)."""
        query = select(OwnerInvoice)
        if owner_id is not None:
            query = query.where(OwnerInvoice.owner_id == owner_id)
        if status is not None:
            query = query.where(OwnerInvoice.status == status)
        if booking_code is not None:
            query = query.where(OwnerInvoice.booking_code == booking_code)
        if after is not None:
            query = query.where(OwnerInvoice.public_id < after)
        rows = await self._db.scalars(
            query.order_by(OwnerInvoice.public_id.desc()).limit(limit + 1)
        )
        return list(rows)

    async def of_owner(self, owner_id: int) -> list[OwnerInvoice]:
        rows = await self._db.scalars(
            select(OwnerInvoice).where(OwnerInvoice.owner_id == owner_id).order_by(OwnerInvoice.id)
        )
        return list(rows)

    async def fees_by_week(self, start: datetime, end: datetime) -> dict[date, int]:
        """Placement fees invoiced in ``[start, end)``, before GST, by the Monday (India time) of
        their week."""
        week = func.date(func.date_trunc("week", func.timezone(INDIA_ZONE, OwnerInvoice.issued_at)))
        rows = await self._db.execute(
            select(week, func.sum(OwnerInvoice.fee_paise))
            .where(OwnerInvoice.issued_at >= start, OwnerInvoice.issued_at < end)
            .group_by(week)
        )
        return {row[0]: int(row[1] or 0) for row in rows}
