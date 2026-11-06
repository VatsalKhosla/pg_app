"""owner area

Revision ID: b5e1d9c3a7f4
Revises: a3c9e7d15f62
Create Date: 2026-11-06 12:00:00.000000

The owner's side of a listing (Phase 7, ADR 0063): the licence and society permission owners
upload for their PGs, with ops' word on each; and how often each PG's page is opened, one row a
PG a day.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "b5e1d9c3a7f4"
down_revision: str | Sequence[str] | None = "a3c9e7d15f62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _stamps() -> list[sa.Column[Any]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "property_documents",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("media_asset_id", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_stamps(),
        sa.CheckConstraint(
            "kind IN ('licence', 'society_permission')", name=op.f("ck_property_documents_kind")
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'accepted', 'rejected')",
            name=op.f("ck_property_documents_status"),
        ),
        sa.CheckConstraint(
            "(status = 'submitted') = (reviewed_at IS NULL)"
            " AND (reviewed_at IS NULL) = (reviewed_by IS NULL)",
            name=op.f("ck_property_documents_reviewed"),
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_property_documents_property_id_properties"),
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_property_documents_media_asset_id_media_assets"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f("fk_property_documents_uploaded_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name=op.f("fk_property_documents_reviewed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_documents")),
        sa.UniqueConstraint("media_asset_id", name=op.f("uq_property_documents_media_asset_id")),
        sa.UniqueConstraint("public_id", name=op.f("uq_property_documents_public_id")),
    )
    op.create_index(
        "ix_property_documents_property_id",
        "property_documents",
        ["property_id", "public_id"],
        unique=False,
    )
    op.create_index(
        "ix_property_documents_uploaded_by", "property_documents", ["uploaded_by"], unique=False
    )
    op.create_index(
        "ix_property_documents_reviewed_by", "property_documents", ["reviewed_by"], unique=False
    )
    op.create_table(
        "property_view_days",
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        *_stamps(),
        sa.CheckConstraint("views > 0", name=op.f("ck_property_view_days_views")),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_property_view_days_property_id_properties"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_view_days")),
        sa.UniqueConstraint("property_id", "day", name="uq_property_view_days_property_day"),
    )


def downgrade() -> None:
    op.drop_table("property_view_days")
    op.drop_index("ix_property_documents_reviewed_by", table_name="property_documents")
    op.drop_index("ix_property_documents_uploaded_by", table_name="property_documents")
    op.drop_index("ix_property_documents_property_id", table_name="property_documents")
    op.drop_table("property_documents")
