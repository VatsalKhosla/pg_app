"""owner agreements

Revision ID: 3fda18ae2d09
Revises: d08fa33c6cea
Create Date: 2026-10-27 12:24:03.916660

The owner agreement (step 2.6, ADR 0025): each time an owner accepts a version, a row records the
version, the SHA-256 of the exact text they were shown, when, the IP and the user agent. The rows
are the evidence of what was agreed, so, like the audit log, the table refuses updates, deletes
and truncation. Owners are never deleted, so their acceptances stay.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3fda18ae2d09"
down_revision: str | Sequence[str] | None = "d08fa33c6cea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_agreements",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("document_sha256", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_ip", sa.Text(), nullable=False),
        sa.Column("accepted_user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "version ~ '^[a-z0-9][a-z0-9.-]{0,63}$'", name=op.f("ck_owner_agreements_version")
        ),
        sa.CheckConstraint(
            "document_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_owner_agreements_document_sha256")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owners.id"], name=op.f("fk_owner_agreements_owner_id_owners")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owner_agreements")),
    )
    op.create_index(
        "ix_owner_agreements_owner_id_accepted_at", "owner_agreements", ["owner_id", "accepted_at"]
    )
    op.execute(
        """
        CREATE FUNCTION owner_agreements_refuse_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'owner_agreements is append-only: % refused', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER owner_agreements_append_only BEFORE UPDATE OR DELETE ON owner_agreements"
        " FOR EACH ROW EXECUTE FUNCTION owner_agreements_refuse_change()"
    )
    op.execute(
        "CREATE TRIGGER owner_agreements_no_truncate BEFORE TRUNCATE ON owner_agreements"
        " FOR EACH STATEMENT EXECUTE FUNCTION owner_agreements_refuse_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER owner_agreements_no_truncate ON owner_agreements")
    op.execute("DROP TRIGGER owner_agreements_append_only ON owner_agreements")
    op.execute("DROP FUNCTION owner_agreements_refuse_change()")
    op.drop_index("ix_owner_agreements_owner_id_accepted_at", table_name="owner_agreements")
    op.drop_table("owner_agreements")
