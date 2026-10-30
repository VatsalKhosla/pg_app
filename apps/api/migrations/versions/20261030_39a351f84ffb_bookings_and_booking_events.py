"""bookings and booking events

Revision ID: 39a351f84ffb
Revises: 45aac3bc7930
Create Date: 2026-10-30 20:02:50.496525

Bookings and what happened to each (ADR 0046). ``booking_events`` is append-only: a trigger
refuses changing or removing a row. The allocations' booking foreign key arrives with bookings.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "39a351f84ffb"
down_revision: str | Sequence[str] | None = "45aac3bc7930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = (
    "'held', 'token_secured', 'confirmed', 'checked_in', 'disputed', 'active', 'completed',"
    " 'expired', 'cancelled', 'rejected', 'no_show', 'refunded'"
)
EVENTS = (
    "'hold', 'token_secured', 'hold_expired', 'cancel', 'confirm', 'reject', 'confirm_timeout',"
    " 'cancel_late', 'owner_cancel', 'check_in', 'no_show', 'dispute', 'window_elapsed',"
    " 'resolve_refund', 'resolve_uphold', 'move_out', 'late_payment_revive', 'late_payment_refund'"
)
EVENTS_NEVER_CHANGE = """
CREATE FUNCTION booking_events_refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'booking_events is append-only: % refused', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END
$$
"""


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("room_category_id", sa.BigInteger(), nullable=False),
        sa.Column("bed_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("quote_id", sa.BigInteger(), nullable=False),
        sa.Column("booking_policy_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("visit_id", sa.BigInteger(), nullable=True),
        sa.Column("move_in", sa.Date(), nullable=False),
        sa.Column("stay_months", sa.Integer(), nullable=False),
        sa.Column("planned_move_out", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirm_by", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_window_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Text(), nullable=True),
        sa.Column("cancellation_kind", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moved_out_on", sa.Date(), nullable=True),
        sa.Column("monthly_rent_paise", sa.BigInteger(), nullable=False),
        sa.Column("fee_paise", sa.BigInteger(), nullable=False),
        sa.Column("gst_paise", sa.BigInteger(), nullable=False),
        sa.Column("owner_fee_total_paise", sa.BigInteger(), nullable=False),
        sa.Column("token_paise", sa.BigInteger(), nullable=False),
        sa.Column("due_at_move_in_paise", sa.BigInteger(), nullable=False),
        sa.Column("deposit_paise", sa.BigInteger(), nullable=False),
        sa.Column("monthly_charges_paise", sa.BigInteger(), nullable=False),
        sa.Column("one_time_charges_paise", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
            "(channel = 'on_spot') = (visit_id IS NOT NULL)", name=op.f("ck_bookings_visit")
        ),
        sa.CheckConstraint(
            "cancelled_by IS NULL OR cancelled_by IN ('student', 'owner', 'ops', 'system')",
            name=op.f("ck_bookings_cancelled_by"),
        ),
        sa.CheckConstraint("channel IN ('on_spot', 'remote')", name=op.f("ck_bookings_channel")),
        sa.CheckConstraint(
            f"status IN ({STATUSES})",
            name=op.f("ck_bookings_status"),
        ),
        sa.CheckConstraint(
            "monthly_rent_paise > 0 AND fee_paise >= 0 AND gst_paise >= 0"
            " AND owner_fee_total_paise >= 0 AND token_paise >= 0 AND deposit_paise >= 0"
            " AND monthly_charges_paise >= 0 AND one_time_charges_paise >= 0",
            name=op.f("ck_bookings_amounts"),
        ),
        sa.CheckConstraint(
            "stay_months > 0 AND planned_move_out > move_in", name=op.f("ck_bookings_stay")
        ),
        sa.CheckConstraint(
            "token_paise + due_at_move_in_paise = monthly_rent_paise",
            name=op.f("ck_bookings_token_and_rest"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_bookings_version")),
        sa.ForeignKeyConstraint(["bed_id"], ["beds.id"], name=op.f("fk_bookings_bed_id_beds")),
        sa.ForeignKeyConstraint(
            ["booking_policy_id"],
            ["booking_policies.id"],
            name=op.f("fk_bookings_booking_policy_id_booking_policies"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owners.id"], name=op.f("fk_bookings_owner_id_owners")
        ),
        sa.ForeignKeyConstraint(
            ["property_id"], ["properties.id"], name=op.f("fk_bookings_property_id_properties")
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"], ["price_quotes.id"], name=op.f("fk_bookings_quote_id_price_quotes")
        ),
        sa.ForeignKeyConstraint(
            ["room_category_id"],
            ["room_categories.id"],
            name=op.f("fk_bookings_room_category_id_room_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name=op.f("fk_bookings_student_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["visit_id"], ["visits.id"], name=op.f("fk_bookings_visit_id_visits")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookings")),
        sa.UniqueConstraint("code", name=op.f("uq_bookings_code")),
        sa.UniqueConstraint("public_id", name=op.f("uq_bookings_public_id")),
        sa.UniqueConstraint("quote_id", name=op.f("uq_bookings_quote_id")),
    )
    op.create_index("ix_bookings_bed_id", "bookings", ["bed_id"], unique=False)
    op.create_index(
        "ix_bookings_booking_policy_id", "bookings", ["booking_policy_id"], unique=False
    )
    op.create_index(
        "ix_bookings_held",
        "bookings",
        ["status", "hold_expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'held'"),
    )
    op.create_index("ix_bookings_owner_id", "bookings", ["owner_id"], unique=False)
    op.create_index("ix_bookings_property_id", "bookings", ["property_id"], unique=False)
    op.create_index("ix_bookings_room_category_id", "bookings", ["room_category_id"], unique=False)
    op.create_index("ix_bookings_student_id", "bookings", ["student_id"], unique=False)
    op.create_index("ix_bookings_visit_id", "bookings", ["visit_id"], unique=False)
    op.create_table(
        "booking_events",
        sa.Column("booking_id", sa.BigInteger(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
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
            "(event = 'hold') = (from_status IS NULL)", name=op.f("ck_booking_events_hold")
        ),
        sa.CheckConstraint(
            "actor_type IN ('student', 'owner', 'ops', 'system')",
            name=op.f("ck_booking_events_actor_type"),
        ),
        sa.CheckConstraint(
            f"event IN ({EVENTS})",
            name=op.f("ck_booking_events_event"),
        ),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({STATUSES})",
            name=op.f("ck_booking_events_from_status"),
        ),
        sa.CheckConstraint(
            f"to_status IN ({STATUSES})",
            name=op.f("ck_booking_events_to_status"),
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_booking_events_booking_id_bookings")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_events")),
    )
    op.create_index("ix_booking_events_booking_id", "booking_events", ["booking_id"], unique=False)
    op.create_index(
        "ix_booking_events_created_at",
        "booking_events",
        ["created_at"],
        unique=False,
        postgresql_using="brin",
    )
    op.execute(EVENTS_NEVER_CHANGE)
    op.execute(
        "CREATE TRIGGER booking_events_append_only BEFORE UPDATE OR DELETE ON booking_events"
        " FOR EACH ROW EXECUTE FUNCTION booking_events_refuse_change()"
    )
    op.create_foreign_key(
        op.f("fk_inventory_allocations_booking_id_bookings"),
        "inventory_allocations",
        "bookings",
        ["booking_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_inventory_allocations_booking_id_bookings"),
        "inventory_allocations",
        type_="foreignkey",
    )
    op.execute("DROP TRIGGER booking_events_append_only ON booking_events")
    op.execute("DROP FUNCTION booking_events_refuse_change()")
    op.drop_index(
        "ix_booking_events_created_at", table_name="booking_events", postgresql_using="brin"
    )
    op.drop_index("ix_booking_events_booking_id", table_name="booking_events")
    op.drop_table("booking_events")
    op.drop_index("ix_bookings_visit_id", table_name="bookings")
    op.drop_index("ix_bookings_student_id", table_name="bookings")
    op.drop_index("ix_bookings_room_category_id", table_name="bookings")
    op.drop_index("ix_bookings_property_id", table_name="bookings")
    op.drop_index("ix_bookings_owner_id", table_name="bookings")
    op.drop_index(
        "ix_bookings_held", table_name="bookings", postgresql_where=sa.text("status = 'held'")
    )
    op.drop_index("ix_bookings_booking_policy_id", table_name="bookings")
    op.drop_index("ix_bookings_bed_id", table_name="bookings")
    op.drop_table("bookings")
