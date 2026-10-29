"""price quotes

Revision ID: a3f9abd16a43
Revises: 93348d6930b2
Create Date: 2026-10-30 02:41:25.307610

Quotes (ADR 0039): the engine\'s answer for a room category, move-in and stay, with all it was
worked out from. A trigger refuses any change to one once made (rule 5).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3f9abd16a43"
down_revision: str | Sequence[str] | None = "93348d6930b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUOTES_NEVER_CHANGE = """
CREATE FUNCTION price_quotes_never_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'a quote never changes once made' USING ERRCODE = 'check_violation';
END
$$
"""


def upgrade() -> None:
    op.create_table(
        "price_quotes",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("room_category_id", sa.BigInteger(), nullable=False),
        sa.Column("move_in", sa.Date(), nullable=False),
        sa.Column("stay_months", sa.Integer(), nullable=False),
        sa.Column("quoted_on", sa.Date(), nullable=False),
        sa.Column("occupancy_bps", sa.Integer(), nullable=False),
        sa.Column("base_rent_paise", sa.BigInteger(), nullable=False),
        sa.Column("monthly_rent_paise", sa.BigInteger(), nullable=False),
        sa.Column("premium_bps", sa.Integer(), nullable=False),
        sa.Column("discount_bps", sa.Integer(), nullable=False),
        sa.Column("adjustments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("clamps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fee_paise", sa.BigInteger(), nullable=False),
        sa.Column("gst_paise", sa.BigInteger(), nullable=False),
        sa.Column("owner_fee_total_paise", sa.BigInteger(), nullable=False),
        sa.Column("token_paise", sa.BigInteger(), nullable=False),
        sa.Column("due_at_move_in_paise", sa.BigInteger(), nullable=False),
        sa.Column("deposit_paise", sa.BigInteger(), nullable=False),
        sa.Column("mandatory_charges", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("monthly_charges_paise", sa.BigInteger(), nullable=False),
        sa.Column("one_time_charges_paise", sa.BigInteger(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("rule_set_id", sa.BigInteger(), nullable=True),
        sa.Column("fee_policy_id", sa.BigInteger(), nullable=False),
        sa.Column("booking_policy_id", sa.BigInteger(), nullable=False),
        sa.Column("pricing_caps_id", sa.BigInteger(), nullable=False),
        sa.Column("rent_band_id", sa.BigInteger(), nullable=True),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("inputs_sha256", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "inputs_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_price_quotes_inputs_sha256")
        ),
        sa.CheckConstraint(
            "base_rent_paise > 0 AND monthly_rent_paise > 0 AND fee_paise >= 0"
            " AND gst_paise >= 0 AND owner_fee_total_paise >= 0 AND token_paise >= 0"
            " AND deposit_paise >= 0 AND monthly_charges_paise >= 0"
            " AND one_time_charges_paise >= 0",
            name=op.f("ck_price_quotes_amounts"),
        ),
        sa.CheckConstraint(
            "stay_months > 0 AND move_in >= quoted_on", name=op.f("ck_price_quotes_stay")
        ),
        sa.CheckConstraint(
            "token_paise + due_at_move_in_paise = monthly_rent_paise",
            name=op.f("ck_price_quotes_token_and_rest"),
        ),
        sa.ForeignKeyConstraint(
            ["booking_policy_id"],
            ["booking_policies.id"],
            name=op.f("fk_price_quotes_booking_policy_id_booking_policies"),
        ),
        sa.ForeignKeyConstraint(
            ["fee_policy_id"],
            ["fee_policies.id"],
            name=op.f("fk_price_quotes_fee_policy_id_fee_policies"),
        ),
        sa.ForeignKeyConstraint(
            ["pricing_caps_id"],
            ["pricing_caps.id"],
            name=op.f("fk_price_quotes_pricing_caps_id_pricing_caps"),
        ),
        sa.ForeignKeyConstraint(
            ["property_id"], ["properties.id"], name=op.f("fk_price_quotes_property_id_properties")
        ),
        sa.ForeignKeyConstraint(
            ["rent_band_id"],
            ["rent_bands.id"],
            name=op.f("fk_price_quotes_rent_band_id_rent_bands"),
        ),
        sa.ForeignKeyConstraint(
            ["room_category_id"],
            ["room_categories.id"],
            name=op.f("fk_price_quotes_room_category_id_room_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id"],
            ["pricing_rule_sets.id"],
            name=op.f("fk_price_quotes_rule_set_id_pricing_rule_sets"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_price_quotes_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_quotes")),
        sa.UniqueConstraint("public_id", name=op.f("uq_price_quotes_public_id")),
    )
    op.create_index("ix_price_quotes_expires_at", "price_quotes", ["expires_at"], unique=False)
    op.create_index(
        "ix_price_quotes_room_category_id", "price_quotes", ["room_category_id"], unique=False
    )

    op.execute(QUOTES_NEVER_CHANGE)
    op.execute(
        "CREATE TRIGGER price_quotes_never_change BEFORE UPDATE ON price_quotes"
        " FOR EACH ROW EXECUTE FUNCTION price_quotes_never_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER price_quotes_never_change ON price_quotes")
    op.execute("DROP FUNCTION price_quotes_never_change()")
    op.drop_index("ix_price_quotes_room_category_id", table_name="price_quotes")
    op.drop_index("ix_price_quotes_expires_at", table_name="price_quotes")
    op.drop_table("price_quotes")
