"""property media

Revision ID: 929c70696e3d
Revises: 7834553760cb
Create Date: 2026-10-24 22:35:35.253688

A listing's photos and videos, in order (step 2.4, ADR 0023): the media module's assets, attached
to a property; the first is the cover. A property's rows go with it.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "929c70696e3d"
down_revision: str | Sequence[str] | None = "7834553760cb"
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


def upgrade() -> None:
    op.create_table(
        "property_media",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("media_asset_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("position >= 0", name=op.f("ck_property_media_position")),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_property_media_property_id_properties"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_property_media_media_asset_id_media_assets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_media")),
        sa.UniqueConstraint(
            "property_id",
            "media_asset_id",
            name=op.f("uq_property_media_property_id_media_asset_id"),
        ),
    )
    op.create_index("ix_property_media_media_asset_id", "property_media", ["media_asset_id"])


def downgrade() -> None:
    op.drop_table("property_media")
