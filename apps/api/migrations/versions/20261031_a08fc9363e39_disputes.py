"""disputes

Revision ID: a08fc9363e39
Revises: b059d241c6b2
Create Date: 2026-10-31 13:57:07.580091

Students' reports that their room isn't as shown, with their photos, and how ops settled each
(step 5.7, ADR 0051). A booking has one at most; ops' queue reads the open ones, oldest first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a08fc9363e39"
down_revision: str | Sequence[str] | None = "b059d241c6b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "disputes",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "(status = 'open') = (resolved_at IS NULL AND resolved_by IS NULL)",
            name=op.f("ck_disputes_resolved"),
        ),
        sa.CheckConstraint(
            "reason IN ('not_as_shown', 'unsafe', 'other')", name=op.f("ck_disputes_reason")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved_refund', 'resolved_uphold')",
            name=op.f("ck_disputes_status"),
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_disputes_booking_id_bookings")
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.id"], name=op.f("fk_disputes_resolved_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disputes")),
        sa.UniqueConstraint("booking_id", name=op.f("uq_disputes_booking_id")),
        sa.UniqueConstraint("public_id", name=op.f("uq_disputes_public_id")),
    )
    op.create_index(
        "ix_disputes_open",
        "disputes",
        ["public_id"],
        unique=False,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index("ix_disputes_resolved_by", "disputes", ["resolved_by"], unique=False)
    op.create_table(
        "dispute_photos",
        sa.Column("dispute_id", sa.BigInteger(), nullable=False),
        sa.Column("media_asset_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
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
        sa.CheckConstraint("position >= 0", name=op.f("ck_dispute_photos_position")),
        sa.ForeignKeyConstraint(
            ["dispute_id"],
            ["disputes.id"],
            name=op.f("fk_dispute_photos_dispute_id_disputes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_dispute_photos_media_asset_id_media_assets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dispute_photos")),
        sa.UniqueConstraint(
            "dispute_id", "media_asset_id", name=op.f("uq_dispute_photos_dispute_id_media_asset_id")
        ),
    )
    op.create_index(
        "ix_dispute_photos_media_asset_id", "dispute_photos", ["media_asset_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_dispute_photos_media_asset_id", table_name="dispute_photos")
    op.drop_table("dispute_photos")
    op.drop_index("ix_disputes_resolved_by", table_name="disputes")
    op.drop_index(
        "ix_disputes_open", table_name="disputes", postgresql_where=sa.text("status = 'open'")
    )
    op.drop_table("disputes")
