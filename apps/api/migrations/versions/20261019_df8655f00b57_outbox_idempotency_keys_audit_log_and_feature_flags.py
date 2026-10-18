"""outbox, idempotency keys, audit log and feature flags

Revision ID: df8655f00b57
Revises: 07106bb150e6
Create Date: 2026-10-19 00:09:11.000000

The core tables of step 0.4 (ARCHITECTURE §5, §6). ``audit_logs`` is append-only: a trigger
refuses UPDATE, DELETE and TRUNCATE for every role, the application's included.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "df8655f00b57"
down_revision: str | Sequence[str] | None = "07106bb150e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity() -> sa.Column[int]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _created_at() -> sa.Column[datetime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _updated_at() -> sa.Column[datetime]:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "outbox_jobs",
        _identity(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'dead')", name=op.f("ck_outbox_jobs_status")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_outbox_jobs_attempts")),
        sa.CheckConstraint("max_attempts > 0", name=op.f("ck_outbox_jobs_max_attempts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_jobs")),
    )
    op.create_index("ix_outbox_jobs_status_run_at", "outbox_jobs", ["status", "run_at"])
    op.create_index(
        "uq_outbox_jobs_dedupe_key",
        "outbox_jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )

    op.create_table(
        "idempotency_keys",
        _identity(),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("request_sha256", sa.Text(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("scope", "key", name=op.f("uq_idempotency_keys_scope_key")),
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])

    op.create_table(
        "audit_logs",
        _identity(),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        _created_at(),
        sa.CheckConstraint(
            "actor_type IN ('user', 'owner', 'staff', 'system')",
            name=op.f("ck_audit_logs_actor_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index(
        "ix_audit_logs_created_at", "audit_logs", ["created_at"], postgresql_using="brin"
    )
    op.execute(
        """
        CREATE FUNCTION audit_logs_refuse_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only: % refused', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs"
        " FOR EACH ROW EXECUTE FUNCTION audit_logs_refuse_change()"
    )
    op.execute(
        "CREATE TRIGGER audit_logs_no_truncate BEFORE TRUNCATE ON audit_logs"
        " FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_refuse_change()"
    )

    op.create_table(
        "feature_flags",
        _identity(),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feature_flags")),
        sa.UniqueConstraint("key", name=op.f("uq_feature_flags_key")),
    )


def downgrade() -> None:
    op.drop_table("feature_flags")
    op.execute("DROP TRIGGER audit_logs_no_truncate ON audit_logs")
    op.execute("DROP TRIGGER audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION audit_logs_refuse_change()")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index("uq_outbox_jobs_dedupe_key", table_name="outbox_jobs")
    op.drop_index("ix_outbox_jobs_status_run_at", table_name="outbox_jobs")
    op.drop_table("outbox_jobs")
