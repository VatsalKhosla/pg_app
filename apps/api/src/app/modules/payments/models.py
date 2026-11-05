"""The payments module's tables (ARCHITECTURE §6; steps 6.1 to 6.3, ADRs 0056, 0057 and 0059)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import text as sql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.ids import new_public_id
from app.modules.payments.domain.payments import PaymentMode, PaymentPurpose, PaymentStatus
from app.modules.payments.domain.refunds import RefundKind, RefundStatus

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


class PaymentEvent(Model):
    """A verified webhook, once: stored as it's acknowledged, then processed by a job. Only what
    the rules need is kept (kept_payload), since the gateway's copy holds personal details."""

    __tablename__ = "payment_events"

    provider: Mapped[str] = mapped_column(Text)
    provider_event_id: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why it moved nothing, when someone should look: it's no order of ours, say.
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_payment_events_provider_event"),
    )


class Refund(Model):
    """Money given back of a payment: asked for here and sent by a job, or found at the gateway."""

    __tablename__ = "refunds"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    payment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payments.id"))
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    # What the booking's change was, or ops' own words.
    reason: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    provider_refund_id: Mapped[str | None] = mapped_column(Text)
    # What a student can quote to their bank.
    reference: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why it failed, or why it was declined.
    failure: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("kind", RefundKind), name="kind"),
        CheckConstraint(_one_of("status", RefundStatus), name="status"),
        CheckConstraint("amount_paise > 0", name="amount"),
        # Two people means two people, whatever the code does.
        CheckConstraint("approved_by IS NULL OR approved_by <> requested_by", name="two_people"),
        CheckConstraint("(status = 'processed') = (processed_at IS NOT NULL)", name="processed"),
        Index("ix_refunds_payment_id", "payment_id"),
        Index("ix_refunds_requested_by", "requested_by"),
        Index("ix_refunds_approved_by", "approved_by"),
        # Ops' queue, by status, oldest first.
        Index("ix_refunds_status", "status", "public_id"),
        Index(
            "uq_refunds_provider_refund_id",
            "provider_refund_id",
            unique=True,
            postgresql_where=sql("provider_refund_id IS NOT NULL"),
        ),
    )
