"""pricing alerts

Revision ID: 6aeece43d6a2
Revises: a3f9abd16a43
Create Date: 2026-10-30 14:49:37.893772

Pricing's integrity alerts (ADR 0043): a rent far below its market, a week of quotes often held
back by a limit, rules that keep changing. The unique key raises each one once.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6aeece43d6a2"
down_revision: str | Sequence[str] | None = "a3f9abd16a43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pricing_alerts",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("room_category_id", sa.BigInteger(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolution", sa.Text(), server_default="", nullable=False),
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
            "kind IN ('rent_below_market', 'clamps_frequent', 'rule_churn')",
            name=op.f("ck_pricing_alerts_kind"),
        ),
        sa.CheckConstraint(
            "char_length(resolution) <= 500", name=op.f("ck_pricing_alerts_resolution")
        ),
        sa.CheckConstraint(
            "resolved_at IS NOT NULL OR resolved_by IS NULL",
            name=op.f("ck_pricing_alerts_resolved"),
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_pricing_alerts_property_id_properties"),
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_pricing_alerts_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["room_category_id"],
            ["room_categories.id"],
            name=op.f("fk_pricing_alerts_room_category_id_room_categories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_alerts")),
        sa.UniqueConstraint("key", name=op.f("uq_pricing_alerts_key")),
        sa.UniqueConstraint("public_id", name=op.f("uq_pricing_alerts_public_id")),
    )
    op.create_index(
        "ix_pricing_alerts_open",
        "pricing_alerts",
        ["kind", "public_id"],
        unique=False,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pricing_alerts_open",
        table_name="pricing_alerts",
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.drop_table("pricing_alerts")
