"""Posting to the books, and reading them (ARCHITECTURE §9.4; step 6.4, ADR 0060).

``Ledger.post`` writes in the caller's transaction, so a money event and its entries commit
together or not at all. Its key means an event can't be posted twice, however many jobs, webhooks or
retries report it.
"""

from typing import TYPE_CHECKING

from opentelemetry import metrics

from app.core.ids import normalize_booking_code
from app.core.pagination import split_page
from app.modules.ledger.domain.ledger import Account, AccountType, Direction, PostingKind
from app.modules.ledger.repository import LedgerRepository
from app.modules.ledger.schemas import (
    LedgerEntryView,
    LedgerTransactionView,
    TrialBalance,
    TrialBalanceLine,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.core.pagination import PageRequest
    from app.modules.ledger.domain.ledger import Posting

_postings = metrics.get_meter("app.ledger").create_counter(
    "ledger.postings", description="Money events posted to the books, by kind"
)


class Ledger:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._clock = clock
        self._ledger = LedgerRepository(db)

    async def post(
        self,
        posting: Posting,
        *,
        key: str,
        booking_id: int | None = None,
        booking_code: str | None = None,
        payment_id: int | None = None,
        memo: str = "",
    ) -> bool:
        """Whether this posted it: False if ``key`` was posted before."""
        transaction = await self._ledger.add_transaction_once(
            kind=posting.kind,
            key=key,
            booking_id=booking_id,
            booking_code=booking_code,
            payment_id=payment_id,
            memo=memo,
            posted_at=self._clock.now(),
        )
        if transaction is None:
            return False
        await self._ledger.add_entries(transaction, posting.lines)
        _postings.add(1, {"kind": posting.kind})
        return True

    async def posted(self, keys: Collection[str]) -> set[str]:
        """Which of these postings' keys are on the books already."""
        return await self._ledger.posted_keys(keys)


class LedgerReader:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._ledger = LedgerRepository(db)

    async def trial_balance(self, booking: str | None) -> TrialBalance:
        """Every account, or what one booking did to each. A code nobody has is all zeros."""
        code = None if booking is None else (normalize_booking_code(booking) or booking)
        async with self._db.begin():
            rows = await self._ledger.trial_balance(code)
        lines = [
            TrialBalanceLine(
                account=Account(row.code),
                name=row.name,
                type=AccountType(row.type),
                debit_paise=int(row.debit),
                credit_paise=int(row.credit),
                balance_paise=int(row.debit) - int(row.credit),
            )
            for row in rows
        ]
        return TrialBalance(
            booking=code,
            lines=lines,
            total_debit_paise=sum(line.debit_paise for line in lines),
            total_credit_paise=sum(line.credit_paise for line in lines),
        )

    async def page(
        self, request: PageRequest, *, booking: str | None
    ) -> tuple[list[LedgerTransactionView], uuid.UUID | None]:
        """Newest first. The same few queries, however long the page."""
        code = None if booking is None else (normalize_booking_code(booking) or booking)
        async with self._db.begin():
            found = await self._ledger.page(
                booking_code=code, after=request.after, limit=request.limit
            )
            items, next_cursor = split_page(found, request, cursor_of=lambda row: row.public_id)
            entries = await self._ledger.entries_of([row.id for row in items])
        return [
            LedgerTransactionView(
                id=row.public_id,
                kind=PostingKind(row.kind),
                booking=row.booking_code,
                memo=row.memo,
                posted_at=row.posted_at,
                entries=[
                    LedgerEntryView(
                        account=Account(account.code),
                        name=account.name,
                        direction=Direction(entry.direction),
                        amount_paise=entry.amount_paise,
                    )
                    for entry, account in entries.get(row.id, [])
                ],
            )
            for row in items
        ], next_cursor
