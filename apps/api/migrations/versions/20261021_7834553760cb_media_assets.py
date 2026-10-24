"""media assets

Revision ID: 7834553760cb
Revises: 485dd7b1db46
Create Date: 2026-10-21 22:23:45.843742

The uploads of step 2.3 (ARCHITECTURE §13, ADR 0022): one row per file, with its purpose and
visibility, where its processing stands, and the variants the worker stored. The files
themselves live in object storage.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7834553760cb"
down_revision: str | Sequence[str] | None = "485dd7b1db46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _one_of(column: str, values: Sequence[str]) -> sa.CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({allowed})", name=op.f(f"ck_media_assets_{column}"))


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("moderation", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("renditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verified_capture", sa.Boolean(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _one_of("purpose", ("listing_photo", "listing_video", "document")),
        _one_of("visibility", ("public", "private")),
        _one_of("status", ("awaiting_upload", "processing", "ready", "rejected")),
        _one_of("moderation", ("pending", "approved", "rejected")),
        sa.CheckConstraint("byte_size > 0", name=op.f("ck_media_assets_byte_size")),
        sa.CheckConstraint("width > 0 AND height > 0", name=op.f("ck_media_assets_dimensions")),
        sa.CheckConstraint("duration_ms >= 0", name=op.f("ck_media_assets_duration")),
        sa.CheckConstraint(
            "jsonb_typeof(renditions) = 'array'", name=op.f("ck_media_assets_renditions")
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_media_assets_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
        sa.UniqueConstraint("public_id", name=op.f("uq_media_assets_public_id")),
    )
    op.create_index("ix_media_assets_uploaded_by", "media_assets", ["uploaded_by"])


def downgrade() -> None:
    op.drop_table("media_assets")
