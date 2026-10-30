"""Inventory's table (ARCHITECTURE §6; step 5.1, ADR 0044): which bed is held, by what, when."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy import text as sql
from sqlalchemy.dialects.postgresql import DATERANGE, ExcludeConstraint, Range
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.ids import new_public_id
from app.modules.inventory.domain.allocations import NOTE_MAX_LENGTH, AllocationKind


def _one_of(column: str, values: type[AllocationKind]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class InventoryAllocation(Model):
    """One bed held for ``period`` (``[start, end)``, an open end for until further notice):
    by a booking, an offline tenant or maintenance.

    The exclusion constraint is the double-booking guarantee: no two active allocations of a
    bed share a day, whatever the code above it does. Never work around it. An allocation ends
    by shortening its period, or stops counting by going inactive; it's never deleted.
    """

    __tablename__ = "inventory_allocations"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    bed_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("beds.id"))
    period: Mapped[Range[date]] = mapped_column(DATERANGE)
    kind: Mapped[str] = mapped_column(Text)
    # The booking that holds the bed.
    booking_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bookings.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sql("true"))
    note: Mapped[str] = mapped_column(Text, server_default="")
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    # When ops ended it early, and who.
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint(_one_of("kind", AllocationKind), name="kind"),
        CheckConstraint("NOT isempty(period) AND NOT lower_inf(period)", name="period"),
        CheckConstraint("(kind = 'booking') = (booking_id IS NOT NULL)", name="booking"),
        CheckConstraint(f"char_length(note) <= {NOTE_MAX_LENGTH}", name="note_length"),
        ExcludeConstraint(
            ("bed_id", "="),
            ("period", "&&"),
            using="gist",
            where=sql("is_active"),
            name="ex_inventory_allocations_bed_period",
        ),
        # A bed's allocations, and a booking's.
        Index("ix_inventory_allocations_bed_id", "bed_id"),
        Index("ix_inventory_allocations_booking_id", "booking_id"),
    )
