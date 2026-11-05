"""The ledger's queries. It never commits: services own the transaction."""

from typing import TYPE_CHECKING

from sqlalchemy import case, func, insert, select
from sqlalchemy.dialects.postgresql import insert as upsert

from app.modules.ledger.domain.ledger import Direction
from app.modules.ledger.models import LedgerAccount, LedgerEntry, LedgerTransaction

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Iterable, Sequence
    from datetime import datetime

    from sqlalchemy import Row
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.ledger.domain.ledger import Line


class LedgerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add_transaction_once(
        self,
        *,
        kind: str,
        key: str,
        booking_id: int | None,
        booking_code: str | None,
        payment_id: int | None,
        memo: str,
        posted_at: datetime,
    ) -> int | None:
        """The new transaction's id; None if this key was posted before."""
        return await self._db.scalar(
            upsert(LedgerTransaction)
            .values(
                kind=kind,
                key=key,
                booking_id=booking_id,
                booking_code=booking_code,
                payment_id=payment_id,
                memo=memo,
                posted_at=posted_at,
            )
            .on_conflict_do_nothing(index_elements=[LedgerTransaction.key])
            .returning(LedgerTransaction.id)
        )

    async def add_entries(self, transaction_id: int, lines: Iterable[Line]) -> None:
        """All of a transaction's entries at once, so the database's check sees them together."""
        accounts = await self._db.execute(select(LedgerAccount.code, LedgerAccount.id))
        ids = {row.code: row.id for row in accounts}
        await self._db.execute(
            insert(LedgerEntry),
            [
                {
                    "transaction_id": transaction_id,
                    "account_id": ids[line.account],
                    "direction": line.direction,
                    "amount_paise": line.amount_paise,
                }
                for line in lines
            ],
        )

    async def trial_balance(
        self, booking_code: str | None
    ) -> Sequence[Row[tuple[str, str, str, int, int]]]:
        """Each account with what's been debited and credited to it: all of it, or one booking's.
        An account nothing has touched still has its line."""
        entries = select(LedgerEntry.account_id, LedgerEntry.direction, LedgerEntry.amount_paise)
        if booking_code is not None:
            entries = entries.join(
                LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id
            ).where(LedgerTransaction.booking_code == booking_code)
        scoped = entries.subquery()
        debit = case((scoped.c.direction == Direction.DEBIT, scoped.c.amount_paise), else_=0)
        credit = case((scoped.c.direction == Direction.CREDIT, scoped.c.amount_paise), else_=0)
        rows = await self._db.execute(
            select(
                LedgerAccount.code,
                LedgerAccount.name,
                LedgerAccount.type,
                func.coalesce(func.sum(debit), 0).label("debit"),
                func.coalesce(func.sum(credit), 0).label("credit"),
            )
            .select_from(LedgerAccount)
            .outerjoin(scoped, scoped.c.account_id == LedgerAccount.id)
            .group_by(LedgerAccount.id)
            .order_by(LedgerAccount.id)
        )
        return rows.all()

    async def page(
        self, *, booking_code: str | None, after: uuid.UUID | None, limit: int
    ) -> list[LedgerTransaction]:
        """Transactions newest first, of one booking if asked, ``limit + 1`` of them (the extra says
        there's more)."""
        query = select(LedgerTransaction)
        if booking_code is not None:
            query = query.where(LedgerTransaction.booking_code == booking_code)
        if after is not None:
            query = query.where(LedgerTransaction.public_id < after)
        rows = await self._db.scalars(
            query.order_by(LedgerTransaction.public_id.desc()).limit(limit + 1)
        )
        return list(rows)

    async def entries_of(
        self, transaction_ids: Collection[int]
    ) -> dict[int, list[tuple[LedgerEntry, LedgerAccount]]]:
        if not transaction_ids:
            return {}
        rows = await self._db.execute(
            select(LedgerEntry, LedgerAccount)
            .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
            .where(LedgerEntry.transaction_id.in_(transaction_ids))
            .order_by(LedgerEntry.id)
        )
        found: dict[int, list[tuple[LedgerEntry, LedgerAccount]]] = {}
        for entry, account in rows:
            found.setdefault(entry.transaction_id, []).append((entry, account))
        return found
