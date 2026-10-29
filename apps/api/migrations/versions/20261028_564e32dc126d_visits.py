"""visits

Revision ID: 564e32dc126d
Revises: 0001bd8caf16
Create Date: 2026-10-28 21:38:52.159410

Students' visits to PGs (ADR 0033): the times they offered, the one ops booked with an agent, the
agent's check-in at the building (the visit log), and how it went.
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "564e32dc126d"
down_revision: str | Sequence[str] | None = "0001bd8caf16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visits",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("preferred_starts", postgresql.ARRAY(sa.DateTime(timezone=True)), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_by", sa.BigInteger(), nullable=True),
        sa.Column("agent_id", sa.BigInteger(), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "check_in_position",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=True,
        ),
        sa.Column("check_in_accuracy_m", sa.Integer(), nullable=True),
        sa.Column("check_in_distance_m", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("outcome_note", sa.Text(), server_default="", nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL)",
            name=op.f("ck_visits_cancelled"),
        ),
        sa.CheckConstraint(
            "(status <> 'requested' OR scheduled_at IS NULL)"
            " AND (status NOT IN ('scheduled', 'completed', 'no_show') OR scheduled_at IS NOT NULL)"
            " AND (scheduled_at IS NULL) = (agent_id IS NULL)",
            name=op.f("ck_visits_scheduled"),
        ),
        sa.CheckConstraint(
            "(status IN ('completed', 'no_show'))"
            " = (outcome IS NOT NULL AND finished_at IS NOT NULL AND checked_in_at IS NOT NULL)",
            name=op.f("ck_visits_finished"),
        ),
        sa.CheckConstraint(
            "cancelled_by IN ('student', 'ops')", name=op.f("ck_visits_cancelled_by")
        ),
        sa.CheckConstraint(
            "outcome IN ('interested', 'not_interested', 'student_no_show')",
            name=op.f("ck_visits_outcome"),
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'scheduled', 'completed', 'no_show', 'cancelled')",
            name=op.f("ck_visits_status"),
        ),
        sa.CheckConstraint(
            "(checked_in_at IS NULL) = (check_in_position IS NULL)"
            " AND (checked_in_at IS NULL) = (check_in_accuracy_m IS NULL)"
            " AND (checked_in_at IS NULL) = (check_in_distance_m IS NULL)",
            name=op.f("ck_visits_check_in"),
        ),
        sa.CheckConstraint(
            "cardinality(preferred_starts) BETWEEN 1 AND 3", name=op.f("ck_visits_preferred_starts")
        ),
        sa.CheckConstraint(
            "char_length(outcome_note) <= 500 AND char_length(cancel_reason) <= 500",
            name=op.f("ck_visits_notes"),
        ),
        sa.CheckConstraint(
            "check_in_accuracy_m >= 0 AND check_in_distance_m >= 0",
            name=op.f("ck_visits_distances"),
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["users.id"], name=op.f("fk_visits_agent_id_users")),
        sa.ForeignKeyConstraint(
            ["property_id"], ["properties.id"], name=op.f("fk_visits_property_id_properties")
        ),
        sa.ForeignKeyConstraint(
            ["scheduled_by"], ["users.id"], name=op.f("fk_visits_scheduled_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name=op.f("fk_visits_student_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visits")),
        sa.UniqueConstraint("public_id", name=op.f("uq_visits_public_id")),
    )
    op.create_index(
        "ix_visits_agent_id_scheduled_at", "visits", ["agent_id", "scheduled_at"], unique=False
    )
    op.create_index("ix_visits_property_id", "visits", ["property_id"], unique=False)
    op.create_index(
        "ix_visits_status_requested_at", "visits", ["status", "requested_at"], unique=False
    )
    op.create_index("ix_visits_student_id_status", "visits", ["student_id", "status"], unique=False)
    op.create_index(
        "uq_visits_student_id_property_id_open",
        "visits",
        ["student_id", "property_id"],
        unique=True,
        postgresql_where="status IN ('requested', 'scheduled')",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_visits_student_id_property_id_open",
        table_name="visits",
        postgresql_where="status IN ('requested', 'scheduled')",
    )
    op.drop_index("ix_visits_student_id_status", table_name="visits")
    op.drop_index("ix_visits_status_requested_at", table_name="visits")
    op.drop_index("ix_visits_property_id", table_name="visits")
    op.drop_index("ix_visits_agent_id_scheduled_at", table_name="visits")
    op.drop_table("visits")
