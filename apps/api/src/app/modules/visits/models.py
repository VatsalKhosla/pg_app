"""The visits module's table (ARCHITECTURE §6, §11; ADR 0033)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.ids import new_public_id
from app.modules.visits.domain.visits import (
    MAX_PREFERRED_STARTS,
    NOTE_MAX_LENGTH,
    CancelledBy,
    Outcome,
    StudentVisitStatus,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from enum import StrEnum


def _one_of(column: str, values: Iterable[StrEnum]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class Visit(Model):
    """A student's visit to a PG: the times they offered, the one ops booked with an agent, the
    agent's check-in at the building (the visit log), and how it went, or its cancellation."""

    __tablename__ = "visits"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"))
    student_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(Text)
    preferred_starts: Mapped[list[datetime]] = mapped_column(ARRAY(DateTime(timezone=True)))
    # The student's browser's anonymous analytics id when they asked, if it reports analytics:
    # the visit's later steps are reported under it (ADR 0035).
    analytics_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    agent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    # The visit log: when the agent checked in (the server's clock), where their phone said they
    # were, how sure it was, and how far that was from the building's exact point.
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_in_position: Mapped[WKBElement | None] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False), nullable=True
    )
    check_in_accuracy_m: Mapped[int | None] = mapped_column(Integer)
    check_in_distance_m: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(Text)
    outcome_note: Mapped[str] = mapped_column(Text, server_default="")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str] = mapped_column(Text, server_default="")

    __table_args__ = (
        CheckConstraint(_one_of("status", StudentVisitStatus), name="status"),
        CheckConstraint(_one_of("outcome", Outcome), name="outcome"),
        CheckConstraint(_one_of("cancelled_by", CancelledBy), name="cancelled_by"),
        CheckConstraint(
            f"cardinality(preferred_starts) BETWEEN 1 AND {MAX_PREFERRED_STARTS}",
            name="preferred_starts",
        ),
        # Asked means no time or agent yet, booked (and after) means both; a cancelled visit may
        # have been either. A time and an agent always go together.
        CheckConstraint(
            "(status <> 'requested' OR scheduled_at IS NULL)"
            " AND (status NOT IN ('scheduled', 'completed', 'no_show') OR scheduled_at IS NOT NULL)"
            " AND (scheduled_at IS NULL) = (agent_id IS NULL)",
            name="scheduled",
        ),
        CheckConstraint(
            "(checked_in_at IS NULL) = (check_in_position IS NULL)"
            " AND (checked_in_at IS NULL) = (check_in_accuracy_m IS NULL)"
            " AND (checked_in_at IS NULL) = (check_in_distance_m IS NULL)",
            name="check_in",
        ),
        # Finished means an outcome after a check-in: the agent was there.
        CheckConstraint(
            "(status IN ('completed', 'no_show'))"
            " = (outcome IS NOT NULL AND finished_at IS NOT NULL AND checked_in_at IS NOT NULL)",
            name="finished",
        ),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL)",
            name="cancelled",
        ),
        CheckConstraint(
            f"char_length(outcome_note) <= {NOTE_MAX_LENGTH}"
            f" AND char_length(cancel_reason) <= {NOTE_MAX_LENGTH}",
            name="notes",
        ),
        CheckConstraint("check_in_accuracy_m >= 0 AND check_in_distance_m >= 0", name="distances"),
        # One open visit per student and PG; the count of open ones per student.
        Index(
            "uq_visits_student_id_property_id_open",
            "student_id",
            "property_id",
            unique=True,
            postgresql_where="status IN ('requested', 'scheduled')",
        ),
        Index("ix_visits_student_id_status", "student_id", "status"),
        Index("ix_visits_agent_id_scheduled_at", "agent_id", "scheduled_at"),
        Index("ix_visits_status_requested_at", "status", "requested_at"),
        Index("ix_visits_property_id", "property_id"),
    )
