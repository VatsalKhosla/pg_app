"""The payments module's table (ARCHITECTURE §6; step 6.1, ADR 0056)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy import text as sql
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.ids import new_public_id
from app.modules.payments.domain.payments import PaymentMode, PaymentPurpose, PaymentStatus

if TYPE_CHECKING:
    from collections.abc import Iterable
    from enum import StrEnum


def _one_of(column: str, values: Iterable[StrEnum]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class Payment(Model):
    """Money asked for through a gateway: one order, for an amount the server fixed, with the
    attempt that went through once one has."""

    __tablename__ = "payments"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bookings.id"))
    purpose: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    # What makes asking again find this row rather than make another (token_key).
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    # Empty only between saving this row and the gateway's answer: no call to the gateway happens
    # inside a transaction.
    provider_order_id: Mapped[str | None] = mapped_column(Text)
    provider_payment_id: Mapped[str | None] = mapped_column(Text)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text, server_default=PaymentStatus.CREATED.value)
    # By the app's clock, like the booking's own stamps.
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_one_of("purpose", PaymentPurpose), name="purpose"),
        CheckConstraint(_one_of("mode", PaymentMode), name="mode"),
        CheckConstraint(_one_of("status", PaymentStatus), name="status"),
        CheckConstraint("amount_paise > 0", name="amount"),
        CheckConstraint("(status = 'captured') = (captured_at IS NOT NULL)", name="captured"),
        CheckConstraint(
            "status = 'created' OR provider_payment_id IS NOT NULL", name="provider_payment"
        ),
        Index("ix_payments_booking_id", "booking_id"),
        Index(
            "uq_payments_provider_order_id",
            "provider",
            "provider_order_id",
            unique=True,
            postgresql_where=sql("provider_order_id IS NOT NULL"),
        ),
        Index(
            "uq_payments_provider_payment_id",
            "provider",
            "provider_payment_id",
            unique=True,
            postgresql_where=sql("provider_payment_id IS NOT NULL"),
        ),
    )
