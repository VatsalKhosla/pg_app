"""pricing rule sets

Revision ID: 93348d6930b2
Revises: c60c5641d497
Create Date: 2026-10-30 02:16:59.728938

A PG's pricing rule sets and their rules (ADR 0038): a draft while edited, then active, then
archived. Triggers keep the rules of an active or archived set as they are, and a set from moving
back or being deleted once it has been in force, so a quote that names its set stays explained.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "93348d6930b2"
down_revision: str | Sequence[str] | None = "c60c5641d497"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A rule may be added, changed or removed only while its set is a draft. A set that's gone is
# being deleted itself (a draft, as the next trigger makes sure), and its rules go with it.
RULES_ONLY_IN_DRAFTS = """
CREATE FUNCTION pricing_rules_only_in_drafts() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    set_status text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        SELECT status INTO set_status FROM pricing_rule_sets WHERE id = OLD.rule_set_id;
        IF set_status IS NOT NULL AND set_status <> 'draft' THEN
            RAISE EXCEPTION 'the rules of an % rule set never change', set_status
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        SELECT status INTO set_status FROM pricing_rule_sets WHERE id = NEW.rule_set_id;
        IF set_status IS DISTINCT FROM 'draft' THEN
            RAISE EXCEPTION 'rules go only into a draft rule set'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END
$$
"""

# A set moves only forward (draft to active to archived), only a draft may be deleted, and once in
# force a set keeps its PG, version and history.
SETS_ONLY_FORWARD = """
CREATE FUNCTION pricing_rule_sets_only_forward() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' THEN
            RAISE EXCEPTION 'an % rule set is kept', OLD.status USING ERRCODE = 'check_violation';
        END IF;
        RETURN OLD;
    END IF;
    IF NEW.property_id <> OLD.property_id OR NEW.version <> OLD.version THEN
        RAISE EXCEPTION 'a rule set keeps its PG and version' USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status = 'archived'
        OR (OLD.status = 'active' AND (NEW.status <> 'archived'
            OR NEW.activated_at IS DISTINCT FROM OLD.activated_at
            OR NEW.activated_by IS DISTINCT FROM OLD.activated_by
            OR NEW.note <> OLD.note))
    THEN
        RAISE EXCEPTION 'an % rule set only moves on to archived', OLD.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$
"""


def upgrade() -> None:
    op.create_table(
        "pricing_rule_sets",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.BigInteger(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)",
            name=op.f("ck_pricing_rule_sets_archived"),
        ),
        sa.CheckConstraint(
            "(status = 'draft') = (activated_at IS NULL)",
            name=op.f("ck_pricing_rule_sets_activated"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')", name=op.f("ck_pricing_rule_sets_status")
        ),
        sa.CheckConstraint(
            "char_length(note) <= 500", name=op.f("ck_pricing_rule_sets_note_length")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_pricing_rule_sets_version")),
        sa.ForeignKeyConstraint(
            ["activated_by"],
            ["users.id"],
            name=op.f("fk_pricing_rule_sets_activated_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_pricing_rule_sets_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_pricing_rule_sets_property_id_properties"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_rule_sets")),
        sa.UniqueConstraint("public_id", name=op.f("uq_pricing_rule_sets_public_id")),
    )
    op.create_index(
        "uq_pricing_rule_sets_property_id_active",
        "pricing_rule_sets",
        ["property_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_pricing_rule_sets_property_id_draft",
        "pricing_rule_sets",
        ["property_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_index(
        "uq_pricing_rule_sets_property_id_version",
        "pricing_rule_sets",
        ["property_id", "version"],
        unique=True,
    )
    op.create_table(
        "pricing_rules",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("room_category_ids", postgresql.ARRAY(sa.BigInteger()), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "kind IN ('season', 'occupancy', 'early_bird', 'last_minute', 'length_of_stay',"
            " 'override')",
            name=op.f("ck_pricing_rules_kind"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(label)) BETWEEN 1 AND 40", name=op.f("ck_pricing_rules_label")
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_pricing_rules_position")),
        sa.ForeignKeyConstraint(
            ["rule_set_id"],
            ["pricing_rule_sets.id"],
            name=op.f("fk_pricing_rules_rule_set_id_pricing_rule_sets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_rules")),
        sa.UniqueConstraint("public_id", name=op.f("uq_pricing_rules_public_id")),
    )
    op.create_index(
        "uq_pricing_rules_rule_set_id_position",
        "pricing_rules",
        ["rule_set_id", "position"],
        unique=True,
    )

    op.execute(RULES_ONLY_IN_DRAFTS)
    op.execute(
        "CREATE TRIGGER pricing_rules_only_in_drafts BEFORE INSERT OR UPDATE OR DELETE"
        " ON pricing_rules FOR EACH ROW EXECUTE FUNCTION pricing_rules_only_in_drafts()"
    )
    op.execute(SETS_ONLY_FORWARD)
    op.execute(
        "CREATE TRIGGER pricing_rule_sets_only_forward BEFORE UPDATE OR DELETE"
        " ON pricing_rule_sets FOR EACH ROW EXECUTE FUNCTION pricing_rule_sets_only_forward()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER pricing_rule_sets_only_forward ON pricing_rule_sets")
    op.execute("DROP FUNCTION pricing_rule_sets_only_forward()")
    op.execute("DROP TRIGGER pricing_rules_only_in_drafts ON pricing_rules")
    op.execute("DROP FUNCTION pricing_rules_only_in_drafts()")
    op.drop_index("uq_pricing_rules_rule_set_id_position", table_name="pricing_rules")
    op.drop_table("pricing_rules")
    op.drop_index("uq_pricing_rule_sets_property_id_version", table_name="pricing_rule_sets")
    op.drop_index(
        "uq_pricing_rule_sets_property_id_draft",
        table_name="pricing_rule_sets",
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.drop_index(
        "uq_pricing_rule_sets_property_id_active",
        table_name="pricing_rule_sets",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_table("pricing_rule_sets")
