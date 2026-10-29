"""pricing policies, caps and rent bands

Revision ID: ce5d7b09e10b
Revises: fce328341fc7
Create Date: 2026-10-29 13:05:41.014105

The policies money follows (ADR 0036): the placement fee, the booking terms, the caps on dynamic
prices and locality rent bands, each a table of versions that never overlap in time. The
defaults are seeded by the next migration, a data migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ce5d7b09e10b"
down_revision: str | Sequence[str] | None = "fce328341fc7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_policies",
        sa.Column("token_paise", sa.BigInteger(), nullable=False),
        sa.Column("hold_minutes", sa.Integer(), nullable=False),
        sa.Column("free_cancel_days", sa.Integer(), nullable=False),
        sa.Column("check_window_hours", sa.Integer(), nullable=False),
        sa.Column("confirm_deadline_hours", sa.Integer(), nullable=False),
        sa.Column("no_show_days", sa.Integer(), nullable=False),
        sa.Column("late_cancel_policy", sa.Text(), nullable=False),
        sa.Column("max_active_holds_per_user", sa.Integer(), nullable=False),
        sa.Column("max_advance_days", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_by", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
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
            (sa.text("tstzrange(effective_from, effective_to)"), "&&"),
            using="gist",
            name="ex_booking_policies_in_force",
        ),
        sa.CheckConstraint(
            "late_cancel_policy IN ('refund_full', 'forfeit_to_owner', 'split')",
            name=op.f("ck_booking_policies_late_cancel"),
        ),
        sa.CheckConstraint(
            "char_length(note) <= 500", name=op.f("ck_booking_policies_note_length")
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_booking_policies_effective_order"),
        ),
        sa.CheckConstraint(
            "hold_minutes > 0 AND free_cancel_days >= 0 AND check_window_hours > 0"
            " AND confirm_deadline_hours > 0 AND no_show_days > 0"
            " AND max_active_holds_per_user > 0 AND max_advance_days > 0",
            name=op.f("ck_booking_policies_terms"),
        ),
        sa.CheckConstraint(
            "token_paise BETWEEN 100000 AND 200000", name=op.f("ck_booking_policies_token")
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_booking_policies_changed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_policies")),
        sa.UniqueConstraint("public_id", name=op.f("uq_booking_policies_public_id")),
    )
    op.create_table(
        "fee_policies",
        sa.Column("rate_bps", sa.Integer(), nullable=False),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("gst_rate_bps", sa.Integer(), nullable=False),
        sa.Column("gst_mode", sa.Text(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_by", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
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
            (sa.text("tstzrange(effective_from, effective_to)"), "&&"),
            using="gist",
            name="ex_fee_policies_in_force",
        ),
        sa.CheckConstraint("basis IN ('listed_rent')", name=op.f("ck_fee_policies_basis")),
        sa.CheckConstraint(
            "gst_mode IN ('exclusive', 'inclusive')", name=op.f("ck_fee_policies_gst_mode")
        ),
        sa.CheckConstraint("char_length(note) <= 500", name=op.f("ck_fee_policies_note_length")),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_fee_policies_effective_order"),
        ),
        sa.CheckConstraint(
            "gst_rate_bps BETWEEN 0 AND 10000", name=op.f("ck_fee_policies_gst_rate")
        ),
        sa.CheckConstraint("rate_bps BETWEEN 0 AND 10000", name=op.f("ck_fee_policies_rate")),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_fee_policies_changed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fee_policies")),
        sa.UniqueConstraint("public_id", name=op.f("uq_fee_policies_public_id")),
    )
    op.create_table(
        "pricing_caps",
        sa.Column("max_premium_bps", sa.Integer(), nullable=False),
        sa.Column("max_discount_bps", sa.Integer(), nullable=False),
        sa.Column("rounding_step_paise", sa.BigInteger(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_by", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
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
            (sa.text("tstzrange(effective_from, effective_to)"), "&&"),
            using="gist",
            name="ex_pricing_caps_in_force",
        ),
        sa.CheckConstraint("char_length(note) <= 500", name=op.f("ck_pricing_caps_note_length")),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_pricing_caps_effective_order"),
        ),
        sa.CheckConstraint(
            "max_discount_bps BETWEEN 0 AND 9000", name=op.f("ck_pricing_caps_discount")
        ),
        sa.CheckConstraint(
            "max_premium_bps BETWEEN 0 AND 10000", name=op.f("ck_pricing_caps_premium")
        ),
        sa.CheckConstraint(
            "rounding_step_paise BETWEEN 100 AND 100000 AND rounding_step_paise % 100 = 0",
            name=op.f("ck_pricing_caps_rounding_step"),
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_pricing_caps_changed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_caps")),
        sa.UniqueConstraint("public_id", name=op.f("uq_pricing_caps_public_id")),
    )
    op.create_table(
        "rent_bands",
        sa.Column("locality_id", sa.BigInteger(), nullable=False),
        sa.Column("occupancy", sa.Text(), nullable=False),
        sa.Column("min_rent_paise", sa.BigInteger(), nullable=False),
        sa.Column("max_rent_paise", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), server_default="", nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_by", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
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
            (sa.column("locality_id"), "="),
            (sa.column("occupancy"), "="),
            (sa.text("tstzrange(effective_from, effective_to)"), "&&"),
            using="gist",
            name="ex_rent_bands_in_force",
        ),
        sa.CheckConstraint(
            "char_length(reference) <= 300 AND (source <> 'official' OR reference <> '')",
            name=op.f("ck_rent_bands_reference"),
        ),
        sa.CheckConstraint(
            "occupancy IN ('single', 'double', 'triple', 'quad')",
            name=op.f("ck_rent_bands_occupancy"),
        ),
        sa.CheckConstraint("source IN ('official', 'internal')", name=op.f("ck_rent_bands_source")),
        sa.CheckConstraint("char_length(note) <= 500", name=op.f("ck_rent_bands_note_length")),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_rent_bands_effective_order"),
        ),
        sa.CheckConstraint(
            "min_rent_paise > 0 AND min_rent_paise <= max_rent_paise"
            " AND max_rent_paise <= 20000000",
            name=op.f("ck_rent_bands_rents"),
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_rent_bands_changed_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["locality_id"], ["localities.id"], name=op.f("fk_rent_bands_locality_id_localities")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rent_bands")),
        sa.UniqueConstraint("public_id", name=op.f("uq_rent_bands_public_id")),
    )
    op.create_index("ix_rent_bands_locality_id", "rent_bands", ["locality_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rent_bands_locality_id", table_name="rent_bands")
    op.drop_table("rent_bands")
    op.drop_table("pricing_caps")
    op.drop_table("fee_policies")
    op.drop_table("booking_policies")
