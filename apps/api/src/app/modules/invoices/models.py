"""The invoices module's tables (ARCHITECTURE §6, §9.5; step 6.5, ADR 0061). An invoice's number and
amounts never change once issued: a trigger refuses it, and refuses removing one."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.ids import new_public_id
from app.modules.invoices.domain.invoices import InvoiceStatus


class InvoiceSequence(Model):
    """The last serial given out in a financial year. Taking the next locks the row until the
    transaction ends, so serials run without gaps: one rolled back is given out again."""

    __tablename__ = "invoice_sequences"

    financial_year: Mapped[str] = mapped_column(Text, unique=True)
    last_serial: Mapped[int] = mapped_column(Integer)

    __table_args__ = (CheckConstraint("last_serial > 0", name="last_serial"),)


class OwnerInvoice(Model):
    """What an owner owes for one tenant placed, issued as the booking settled."""

    __tablename__ = "owner_invoices"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("owners.id"))
    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bookings.id"), unique=True)
    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"))
    # As people quote it, so reading an invoice asks nothing of bookings.
    booking_code: Mapped[str] = mapped_column(Text)
    financial_year: Mapped[str] = mapped_column(Text)
    serial: Mapped[int] = mapped_column(Integer)
    number: Mapped[str] = mapped_column(Text, unique=True)
    # The terms the fee was worked out on, from the booking's quote (rules 2 and 3).
    base_rent_paise: Mapped[int] = mapped_column(BigInteger)
    fee_rate_bps: Mapped[int] = mapped_column(Integer)
    gst_rate_bps: Mapped[int] = mapped_column(Integer)
    gst_included: Mapped[bool] = mapped_column(Boolean)
    fee_paise: Mapped[int] = mapped_column(BigInteger)
    gst_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    token_applied_paise: Mapped[int] = mapped_column(BigInteger)
    token_over_paise: Mapped[int] = mapped_column(BigInteger)
    balance_due_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text)
    # By the app's clock.
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The PDF in the private bucket, once a job has made it.
    pdf_key: Mapped[str | None] = mapped_column(Text)
    # Where the balance can be paid now, while it can.
    pay_provider: Mapped[str | None] = mapped_column(Text)
    pay_url: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{status.value}'" for status in InvoiceStatus) + ")",
            name="status",
        ),
        CheckConstraint(
            "base_rent_paise > 0 AND fee_paise > 0 AND gst_paise >= 0"
            " AND token_applied_paise >= 0 AND token_over_paise >= 0 AND balance_due_paise >= 0"
            " AND fee_rate_bps > 0 AND gst_rate_bps >= 0 AND serial > 0",
            name="amounts",
        ),
        CheckConstraint("total_paise = fee_paise + gst_paise", name="total"),
        CheckConstraint("balance_due_paise = total_paise - token_applied_paise", name="balance"),
        CheckConstraint("token_over_paise = 0 OR balance_due_paise = 0", name="token_over"),
        CheckConstraint("(status = 'paid') = (paid_at IS NOT NULL)", name="paid"),
        CheckConstraint("(pay_url IS NULL) = (pay_provider IS NULL)", name="pay"),
        UniqueConstraint("financial_year", "serial", name="uq_owner_invoices_serial"),
        Index("ix_owner_invoices_owner_id", "owner_id", "public_id"),
        Index("ix_owner_invoices_property_id", "property_id"),
        Index("ix_owner_invoices_status", "status", "public_id"),
        Index("ix_owner_invoices_booking_code", "booking_code"),
    )
