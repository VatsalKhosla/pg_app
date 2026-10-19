"""Compliance tables (ARCHITECTURE §6): data requests, and the export files they produce."""

import uuid
from datetime import datetime
from typing import Final

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
from app.modules.compliance.domain.requests import DataRequestKind, DataRequestStatus

# The predicate of the one-open-request-per-kind index.
OPEN_REQUEST: Final = f"status = '{DataRequestStatus.RECEIVED}'"


def _one_of(column: str, values: type[DataRequestKind | DataRequestStatus]) -> str:
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
