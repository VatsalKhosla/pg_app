"""The booking module's tables (ARCHITECTURE §6; step 5.3, ADR 0046): bookings, and what
happened to each."""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy import text as sql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AppendOnlyModel, Model
from app.core.ids import new_public_id
from app.modules.booking.domain.state_machine import BookingEvent, BookingStatus, Party


class Channel(StrEnum):
    # The student at the PG with a field agent, from their visit (5.9).
    ON_SPOT = "on_spot"
    # From the PG's page, while remote booking is on.
    REMOTE = "remote"


# The event a booking's first row records: the hold that made it.
HOLD: Final = "hold"


def _one_of(column: str, values: type[StrEnum] | tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class Booking(Model):
    """A student's booking of a bed, from its hold to its end.

    Its status changes only through the state machine (ADR 0045), saved with a compare-and-set on
    status and version. Its money is the quote's, copied once and never priced again (rule 5),
    and its terms are the booking policy version the quote was made under.
    """

    __tablename__ = "bookings"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    # What people read out to one another, such as BK-7F3K2Q9M.
    code: Mapped[str] = mapped_column(Text, unique=True)
    student_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"))
    room_category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("room_categories.id"))
    bed_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("beds.id"))
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("owners.id"))
    quote_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("price_quotes.id"), unique=True)
    booking_policy_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("booking_policies.id"))
    channel: Mapped[str] = mapped_column(Text)
    visit_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("visits.id"))
    move_in: Mapped[date] = mapped_column(Date)
    stay_months: Mapped[int] = mapped_column(Integer)
    planned_move_out: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text)
    hold_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When the owner must confirm by, once the token is in.
    confirm_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_window_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Who ended it early (a party), and how (the event).
    cancelled_by: Mapped[str | None] = mapped_column(Text)
    cancellation_kind: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moved_out_on: Mapped[date | None] = mapped_column(Date)
    # The quote's money, in paise.
    monthly_rent_paise: Mapped[int] = mapped_column(BigInteger)
    fee_paise: Mapped[int] = mapped_column(BigInteger)
    gst_paise: Mapped[int] = mapped_column(BigInteger)
    owner_fee_total_paise: Mapped[int] = mapped_column(BigInteger)
    token_paise: Mapped[int] = mapped_column(BigInteger)
    due_at_move_in_paise: Mapped[int] = mapped_column(BigInteger)
    deposit_paise: Mapped[int] = mapped_column(BigInteger)
    monthly_charges_paise: Mapped[int] = mapped_column(BigInteger)
    one_time_charges_paise: Mapped[int] = mapped_column(BigInteger)
    version: Mapped[int] = mapped_column(Integer, server_default=sql("1"))

    __table_args__ = (
        CheckConstraint(_one_of("status", BookingStatus), name="status"),
        CheckConstraint(_one_of("channel", Channel), name="channel"),
        CheckConstraint("(channel = 'on_spot') = (visit_id IS NOT NULL)", name="visit"),
        CheckConstraint(
            f"cancelled_by IS NULL OR {_one_of('cancelled_by', Party)}", name="cancelled_by"
        ),
        CheckConstraint(
            "monthly_rent_paise > 0 AND fee_paise >= 0 AND gst_paise >= 0"
            " AND owner_fee_total_paise >= 0 AND token_paise >= 0 AND deposit_paise >= 0"
            " AND monthly_charges_paise >= 0 AND one_time_charges_paise >= 0",
            name="amounts",
        ),
        CheckConstraint(
            "token_paise + due_at_move_in_paise = monthly_rent_paise", name="token_and_rest"
        ),
        CheckConstraint("stay_months > 0 AND planned_move_out > move_in", name="stay"),
        CheckConstraint("version > 0", name="version"),
        Index("ix_bookings_student_id", "student_id"),
        Index("ix_bookings_property_id", "property_id"),
        Index("ix_bookings_room_category_id", "room_category_id"),
        Index("ix_bookings_bed_id", "bed_id"),
        Index("ix_bookings_owner_id", "owner_id"),
        Index("ix_bookings_visit_id", "visit_id"),
        Index("ix_bookings_booking_policy_id", "booking_policy_id"),
        # The holds to expire, and a student's holds.
        Index(
            "ix_bookings_held",
            "status",
            "hold_expires_at",
            postgresql_where=sql("status = 'held'"),
        ),
    )


class BookingEventRecord(AppendOnlyModel):
    """One change to a booking, written with it and never changed (a trigger refuses it): the
    student's timeline and the booking's audit trail."""

    __tablename__ = "booking_events"

    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bookings.id"))
    event: Mapped[str] = mapped_column(Text)
    # None for the hold that made the booking.
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(Text)
    # The user who sent it; None for the system. Not a foreign key, as the audit log's isn't.
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sql("'{}'::jsonb"))

    __table_args__ = (
        CheckConstraint(_one_of("event", (HOLD, *BookingEvent)), name="event"),
        CheckConstraint(
            f"from_status IS NULL OR {_one_of('from_status', BookingStatus)}", name="from_status"
        ),
        CheckConstraint(_one_of("to_status", BookingStatus), name="to_status"),
        CheckConstraint(_one_of("actor_type", Party), name="actor_type"),
        CheckConstraint("(event = 'hold') = (from_status IS NULL)", name="hold"),
        Index("ix_booking_events_booking_id", "booking_id"),
        Index("ix_booking_events_created_at", "created_at", postgresql_using="brin"),
    )
