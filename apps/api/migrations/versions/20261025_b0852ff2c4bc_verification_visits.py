"""verification visits

Revision ID: b0852ff2c4bc
Revises: d928f0d105f9
Create Date: 2026-10-25 22:36:32.508062

Field verification (step 2.5, ADR 0024): a visit is booked by ops for a field agent and holds the
report the agent submits on site (the checklist, the result, where the agent was and how far
from the pin), or its cancellation. A property has one booked visit at a time. The report's
photos are private media, in order. A visit's photos go with it; properties and users are never
deleted, so their visits stay.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "b0852ff2c4bc"
down_revision: str | Sequence[str] | None = "d928f0d105f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERIFICATION_STATUSES = "'unverified', 'scheduled', 'verified', 'rejected', 'suspended'"


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "verification_visits",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("scheduled_by", sa.BigInteger(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("status_before", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", Geography("POINT", srid=4326, spatial_index=False), nullable=True),
        sa.Column("position_accuracy_m", sa.Integer(), nullable=True),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('scheduled', 'submitted', 'cancelled')",
            name=op.f("ck_verification_visits_status"),
        ),
        sa.CheckConstraint(
            f"status_before IN ({VERIFICATION_STATUSES})",
            name=op.f("ck_verification_visits_status_before"),
        ),
        sa.CheckConstraint(
            "result IN ('passed', 'failed')", name=op.f("ck_verification_visits_result")
        ),
        sa.CheckConstraint(
            "(status = 'submitted') = (submitted_at IS NOT NULL AND position IS NOT NULL"
            " AND position_accuracy_m IS NOT NULL AND distance_m IS NOT NULL"
            " AND checklist IS NOT NULL AND result IS NOT NULL)",
            name=op.f("ck_verification_visits_report"),
        ),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name=op.f("ck_verification_visits_cancelled"),
        ),
        sa.CheckConstraint(
            "result IS DISTINCT FROM 'failed' OR notes <> ''",
            name=op.f("ck_verification_visits_failed_notes"),
        ),
        sa.CheckConstraint(
            "position_accuracy_m >= 0 AND distance_m >= 0",
            name=op.f("ck_verification_visits_distances"),
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_verification_visits_property_id_properties"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["users.id"], name=op.f("fk_verification_visits_agent_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["scheduled_by"], ["users.id"], name=op.f("fk_verification_visits_scheduled_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_visits")),
        sa.UniqueConstraint("public_id", name=op.f("uq_verification_visits_public_id")),
    )
    op.create_index(
        "uq_verification_visits_property_id_scheduled",
        "verification_visits",
        ["property_id"],
        unique=True,
        postgresql_where=sa.text("status = 'scheduled'"),
    )
    op.create_index("ix_verification_visits_property_id", "verification_visits", ["property_id"])
    op.create_index(
        "ix_verification_visits_agent_id_status_scheduled_for",
        "verification_visits",
        ["agent_id", "status", "scheduled_for"],
    )
    op.create_index("ix_verification_visits_scheduled_by", "verification_visits", ["scheduled_by"])
    op.create_table(
        "verification_photos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("visit_id", sa.BigInteger(), nullable=False),
        sa.Column("media_asset_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("position >= 0", name=op.f("ck_verification_photos_position")),
        sa.ForeignKeyConstraint(
            ["visit_id"],
            ["verification_visits.id"],
            name=op.f("fk_verification_photos_visit_id_verification_visits"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_verification_photos_media_asset_id_media_assets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_photos")),
        sa.UniqueConstraint(
            "visit_id",
            "media_asset_id",
            name=op.f("uq_verification_photos_visit_id_media_asset_id"),
        ),
    )
    op.create_index(
        "ix_verification_photos_media_asset_id", "verification_photos", ["media_asset_id"]
    )


def downgrade() -> None:
    op.drop_table("verification_photos")
    op.drop_table("verification_visits")
