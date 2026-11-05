"""The ledger's tables (ARCHITECTURE §6, §9.4; step 6.4, ADR 0060). Entries are written once: the
database refuses to change or remove them, and refuses a transaction whose entries don't balance
when it commits (the migration's triggers)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AppendOnlyModel, Model
from app.core.ids import new_public_id
from app.modules.ledger.domain.ledger import AccountType, Direction, PostingKind


def _one_of(column: str, values: type[AccountType | Direction | PostingKind]) -> str:
    return f"{column} IN ({', '.join(f"'{value.value}'" for value in values)})"


class LedgerAccount(Model):
    __tablename__ = "ledger_accounts"

    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)

    __table_args__ = (CheckConstraint(_one_of("type", AccountType), name="type"),)


class LedgerTransaction(AppendOnlyModel):
    """One money event. ``key`` makes posting it twice impossible, whichever job or request does."""

    __tablename__ = "ledger_transactions"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    kind: Mapped[str] = mapped_column(Text)
    key: Mapped[str] = mapped_column(Text, unique=True)
    booking_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bookings.id"))
    # As people quote it. The ledger knows no other module, so it keeps its own copy.
    booking_code: Mapped[str | None] = mapped_column(Text)
    payment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payments.id"))
    memo: Mapped[str] = mapped_column(Text, server_default="")
    # By the app's clock.
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_one_of("kind", PostingKind), name="kind"),
        Index("ix_ledger_transactions_booking_id", "booking_id"),
        Index("ix_ledger_transactions_payment_id", "payment_id"),
        Index("ix_ledger_transactions_booking_code", "booking_code"),
    )


class LedgerEntry(AppendOnlyModel):
    __tablename__ = "ledger_entries"

    transaction_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ledger_transactions.id"))
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ledger_accounts.id"))
    direction: Mapped[str] = mapped_column(Text)
    amount_paise: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint(_one_of("direction", Direction), name="direction"),
        CheckConstraint("amount_paise > 0", name="amount"),
        Index("ix_ledger_entries_transaction_id", "transaction_id"),
        Index("ix_ledger_entries_account_id", "account_id"),
    )
