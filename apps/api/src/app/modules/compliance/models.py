"""Compliance tables (ARCHITECTURE §6): data requests and the export files they produce, and
grievances."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.ids import new_public_id
from app.modules.compliance.domain.grievances import (
    DETAILS_MAX_LENGTH,
    EMAIL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    REFERENCE_MAX_LENGTH,
    REPLY_MAX_LENGTH,
    GrievanceCategory,
    GrievanceStatus,
)
from app.modules.compliance.domain.requests import DataRequestKind, DataRequestStatus

if TYPE_CHECKING:
    from enum import StrEnum

# The predicate of the one-open-request-per-kind index.
OPEN_REQUEST: Final = f"status = '{DataRequestStatus.RECEIVED}'"


def _one_of(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class DataRequest(Model):
    """A person's request for a copy of their data, or for their account's deletion."""

    __tablename__ = "data_requests"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When the export became ready, or ops completed or rejected the deletion.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Export: when the file is deleted.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Deletion: the staff member who resolved it, and the reason they gave.
    resolved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("kind", DataRequestKind), name="kind"),
        CheckConstraint(_one_of("status", DataRequestStatus), name="status"),
        # One open request of each kind per person.
        Index(
            "uq_data_requests_open",
            "user_id",
            "kind",
            unique=True,
            postgresql_where=text(OPEN_REQUEST),
        ),
        Index("ix_data_requests_user_id", "user_id"),
        Index("ix_data_requests_status_requested_at", "status", "requested_at"),
    )


class DataExport(Model):
    """An export's file: the person's data as JSON, deleted when the request expires."""

    __tablename__ = "data_exports"

    data_request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("data_requests.id", ondelete="CASCADE"), unique=True
    )
    content: Mapped[bytes] = mapped_column(LargeBinary)


class Grievance(Model):
    """A complaint to the grievance officer (ADR 0034). It keeps the name and contact it came
    with, so it still says whom to answer if the account is later deleted."""

    __tablename__ = "grievances"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    ticket_number: Mapped[str] = mapped_column(Text, unique=True)
    # The account it came from, when the person was signed in.
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    # Empty when a signed-in person gave none and their account has none.
    name: Mapped[str] = mapped_column(Text)
    phone_e164: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    # What it's about in the person's words: a PG, a visit, a booking code.
    reference: Mapped[str] = mapped_column(Text, server_default="")
    details: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledge_by: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolve_by: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    # The officer's reply to the person.
    reply: Mapped[str] = mapped_column(Text, server_default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    # What was done about it, for the person.
    resolution: Mapped[str] = mapped_column(Text, server_default="")

    __table_args__ = (
        CheckConstraint(_one_of("status", GrievanceStatus), name="status"),
        CheckConstraint(_one_of("category", GrievanceCategory), name="category"),
        CheckConstraint("phone_e164 IS NOT NULL OR email IS NOT NULL", name="contact"),
        # Acknowledged once it's past received, with a reply unless it was resolved at once;
        # resolved with what was done.
        CheckConstraint(
            "(status = 'received') = (acknowledged_at IS NULL)"
            " AND (status <> 'acknowledged' OR reply <> '')",
            name="acknowledged",
        ),
        CheckConstraint(
            "(status = 'resolved') = (resolved_at IS NOT NULL)"
            " AND (status <> 'resolved' OR resolution <> '')",
            name="resolved",
        ),
        CheckConstraint(
            f"char_length(name) <= {NAME_MAX_LENGTH}"
            f" AND char_length(details) BETWEEN 1 AND {DETAILS_MAX_LENGTH}"
            f" AND char_length(reference) <= {REFERENCE_MAX_LENGTH}"
            f" AND char_length(email) <= {EMAIL_MAX_LENGTH}"
            f" AND char_length(reply) <= {REPLY_MAX_LENGTH}"
            f" AND char_length(resolution) <= {REPLY_MAX_LENGTH}",
            name="lengths",
        ),
        Index("ix_grievances_user_id", "user_id"),
        Index("ix_grievances_status_received_at", "status", "received_at"),
    )
