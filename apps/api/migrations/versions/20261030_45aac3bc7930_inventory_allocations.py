"""inventory allocations

Revision ID: 45aac3bc7930
Revises: 6aeece43d6a2
Create Date: 2026-10-30 18:29:13.366446

Inventory allocations (ADR 0044): a bed held for a period by a booking, an offline tenant or
maintenance. The exclusion constraint keeps two active allocations of one bed from sharing a day:
the double-booking guarantee. The booking's foreign key arrives with the bookings table (5.3).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "45aac3bc7930"
down_revision: str | Sequence[str] | None = "6aeece43d6a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_allocations",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("bed_id", sa.BigInteger(), nullable=False),
        sa.Column("period", postgresql.DATERANGE(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.BigInteger(), nullable=True),
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
        postgresql.ExcludeConstraint(
            (sa.column("bed_id"), "="),
            (sa.column("period"), "&&"),
            where=sa.text("is_active"),
            using="gist",
            name="ex_inventory_allocations_bed_period",
        ),
        sa.CheckConstraint(
            "(kind = 'booking') = (booking_id IS NOT NULL)",
            name=op.f("ck_inventory_allocations_booking"),
        ),
        sa.CheckConstraint(
            "kind IN ('booking', 'offline_tenant', 'maintenance')",
            name=op.f("ck_inventory_allocations_kind"),
        ),
        sa.CheckConstraint(
            "NOT isempty(period) AND NOT lower_inf(period)",
            name=op.f("ck_inventory_allocations_period"),
        ),
        sa.CheckConstraint(
            "char_length(note) <= 300", name=op.f("ck_inventory_allocations_note_length")
        ),
        sa.ForeignKeyConstraint(
            ["bed_id"], ["beds.id"], name=op.f("fk_inventory_allocations_bed_id_beds")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_inventory_allocations_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ended_by"],
            ["users.id"],
            name=op.f("fk_inventory_allocations_ended_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_allocations")),
        sa.UniqueConstraint("public_id", name=op.f("uq_inventory_allocations_public_id")),
    )
    op.create_index(
        "ix_inventory_allocations_bed_id", "inventory_allocations", ["bed_id"], unique=False
    )
    op.create_index(
        "ix_inventory_allocations_booking_id", "inventory_allocations", ["booking_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_allocations_booking_id", table_name="inventory_allocations")
    op.drop_index("ix_inventory_allocations_bed_id", table_name="inventory_allocations")
    op.drop_table("inventory_allocations")
