"""rent agreements

Revision ID: ea4c308884f8
Revises: 94f3dd7fce43
Create Date: 2026-11-14 12:00:00.000000

Rent agreements and police verification (ADR 0070): a confirmed booking's leave-and-licence
agreement, the two signatures on it, the one-time codes signers confirm with, and the tenant's
police verification.

The database keeps the record honest: an agreement's hash is checked against its text; a signature
names the text it signed by that hash through a foreign key to the pair, so a signed text can't
change; each side signs once; and, like the audit log, signatures refuse updates, deletes and
truncation. Police-verification details are stored sealed by the application, never in clear.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "ea4c308884f8"
down_revision: str | Sequence[str] | None = "94f3dd7fce43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _updated() -> sa.Column[Any]:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column[Any]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "rental_agreements",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("booking_ended_at", sa.DateTime(timezone=True), nullable=True),
        _updated(),
        _id(),
        _created(),
        sa.CheckConstraint(
            "status IN ('awaiting_signatures', 'signed_by_student', 'signed_by_owner', 'signed',"
            " 'void')",
            name=op.f("ck_rental_agreements_status"),
        ),
        sa.CheckConstraint(
            "text_sha256 = encode(sha256(convert_to(text, 'UTF8')), 'hex')",
            name=op.f("ck_rental_agreements_text_sha256"),
        ),
        sa.CheckConstraint(
            "template_version ~ '^[a-z0-9][a-z0-9.-]{0,63}$'",
            name=op.f("ck_rental_agreements_template_version"),
        ),
        sa.CheckConstraint(
            "(status = 'signed') = (signed_at IS NOT NULL)",
            name=op.f("ck_rental_agreements_signed"),
        ),
        sa.CheckConstraint(
            "(status = 'void') = (voided_at IS NOT NULL)", name=op.f("ck_rental_agreements_void")
        ),
        sa.CheckConstraint(
            "status <> 'void' OR booking_ended_at IS NOT NULL",
            name=op.f("ck_rental_agreements_void_ended"),
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_rental_agreements_booking_id_bookings")
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name=op.f("fk_rental_agreements_student_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owners.id"], name=op.f("fk_rental_agreements_owner_id_owners")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rental_agreements")),
        sa.UniqueConstraint("booking_id", name=op.f("uq_rental_agreements_booking_id")),
        sa.UniqueConstraint("public_id", name=op.f("uq_rental_agreements_public_id")),
        # What signatures refer to: an agreement as it read when they were made.
        sa.UniqueConstraint("id", "text_sha256", name="uq_rental_agreements_id_text_sha256"),
    )
    op.create_index("ix_rental_agreements_student_id", "rental_agreements", ["student_id"])
    op.create_index("ix_rental_agreements_owner_id", "rental_agreements", ["owner_id"])

    op.create_table(
        "agreement_signatures",
        sa.Column("agreement_id", sa.BigInteger(), nullable=False),
        sa.Column("text_sha256", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Text(), nullable=False),
        sa.Column("signer", sa.Text(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("typed_name", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        _id(),
        _created(),
        sa.CheckConstraint(
            "signer IN ('student', 'owner')", name=op.f("ck_agreement_signatures_signer")
        ),
        sa.CheckConstraint(
            "char_length(typed_name) BETWEEN 2 AND 80",
            name=op.f("ck_agreement_signatures_typed_name"),
        ),
        sa.CheckConstraint(
            "text_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_agreement_signatures_text_sha256")
        ),
        sa.ForeignKeyConstraint(
            ["agreement_id", "text_sha256"],
            ["rental_agreements.id", "rental_agreements.text_sha256"],
            name="fk_agreement_signatures_agreement_text",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_agreement_signatures_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agreement_signatures")),
        sa.UniqueConstraint(
            "agreement_id", "signer", name=op.f("uq_agreement_signatures_agreement_id_signer")
        ),
    )
    op.create_index("ix_agreement_signatures_user_id", "agreement_signatures", ["user_id"])
    op.execute(
        """
        CREATE FUNCTION agreement_signatures_refuse_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'agreement_signatures is append-only: % refused', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER agreement_signatures_append_only BEFORE UPDATE OR DELETE"
        " ON agreement_signatures FOR EACH ROW"
        " EXECUTE FUNCTION agreement_signatures_refuse_change()"
    )
    op.execute(
        "CREATE TRIGGER agreement_signatures_no_truncate BEFORE TRUNCATE ON agreement_signatures"
        " FOR EACH STATEMENT EXECUTE FUNCTION agreement_signatures_refuse_change()"
    )

    op.create_table(
        "agreement_signing_codes",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("agreement_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("signer", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        _updated(),
        _id(),
        _created(),
        sa.CheckConstraint(
            "signer IN ('student', 'owner')", name=op.f("ck_agreement_signing_codes_signer")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_agreement_signing_codes_attempts")),
        sa.ForeignKeyConstraint(
            ["agreement_id"],
            ["rental_agreements.id"],
            name=op.f("fk_agreement_signing_codes_agreement_id_rental_agreements"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_agreement_signing_codes_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agreement_signing_codes")),
        sa.UniqueConstraint("public_id", name=op.f("uq_agreement_signing_codes_public_id")),
    )
    op.create_index(
        "ix_agreement_signing_codes_agreement_user",
        "agreement_signing_codes",
        ["agreement_id", "user_id", "requested_at"],
    )
    op.create_index("ix_agreement_signing_codes_user_id", "agreement_signing_codes", ["user_id"])
    op.create_index(
        "ix_agreement_signing_codes_requested_at", "agreement_signing_codes", ["requested_at"]
    )

    op.create_table(
        "tenant_verifications",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("agreement_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("details_sealed", sa.Text(), nullable=True),
        sa.Column("details_submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledgement_media_id", sa.BigInteger(), nullable=True),
        sa.Column("police_reference", sa.Text(), nullable=True),
        sa.Column("submitted_to_police_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True),
        _updated(),
        _id(),
        _created(),
        sa.CheckConstraint(
            "status IN ('not_started', 'details_submitted', 'submitted_to_police', 'verified')"
            " AND status <> 'not_started'",
            name=op.f("ck_tenant_verifications_status"),
        ),
        sa.CheckConstraint(
            "(details_sealed IS NULL) = (erased_at IS NOT NULL)",
            name=op.f("ck_tenant_verifications_erased"),
        ),
        sa.CheckConstraint(
            "(status IN ('submitted_to_police', 'verified'))"
            " = (submitted_to_police_at IS NOT NULL AND acknowledgement_media_id IS NOT NULL"
            " AND submitted_by IS NOT NULL)",
            name=op.f("ck_tenant_verifications_submitted"),
        ),
        sa.CheckConstraint(
            "(status = 'verified') = (verified_at IS NOT NULL AND verified_by IS NOT NULL)",
            name=op.f("ck_tenant_verifications_verified"),
        ),
        sa.CheckConstraint(
            "police_reference IS NULL OR char_length(police_reference) BETWEEN 1 AND 60",
            name=op.f("ck_tenant_verifications_police_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["agreement_id"],
            ["rental_agreements.id"],
            name=op.f("fk_tenant_verifications_agreement_id_rental_agreements"),
        ),
        sa.ForeignKeyConstraint(
            ["acknowledgement_media_id"],
            ["media_assets.id"],
            name=op.f("fk_tenant_verifications_acknowledgement_media_id_media_assets"),
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"], ["users.id"], name=op.f("fk_tenant_verifications_submitted_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"], ["users.id"], name=op.f("fk_tenant_verifications_verified_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_verifications")),
        sa.UniqueConstraint("agreement_id", name=op.f("uq_tenant_verifications_agreement_id")),
        sa.UniqueConstraint(
            "acknowledgement_media_id",
            name=op.f("uq_tenant_verifications_acknowledgement_media_id"),
        ),
        sa.UniqueConstraint("public_id", name=op.f("uq_tenant_verifications_public_id")),
    )
    op.create_index(
        "ix_tenant_verifications_submitted_by", "tenant_verifications", ["submitted_by"]
    )
    op.create_index("ix_tenant_verifications_verified_by", "tenant_verifications", ["verified_by"])


def downgrade() -> None:
    op.drop_index("ix_tenant_verifications_verified_by", table_name="tenant_verifications")
    op.drop_index("ix_tenant_verifications_submitted_by", table_name="tenant_verifications")
    op.drop_table("tenant_verifications")
    op.drop_index("ix_agreement_signing_codes_requested_at", table_name="agreement_signing_codes")
    op.drop_index("ix_agreement_signing_codes_user_id", table_name="agreement_signing_codes")
    op.drop_index("ix_agreement_signing_codes_agreement_user", table_name="agreement_signing_codes")
    op.drop_table("agreement_signing_codes")
    op.execute("DROP TRIGGER agreement_signatures_no_truncate ON agreement_signatures")
    op.execute("DROP TRIGGER agreement_signatures_append_only ON agreement_signatures")
    op.execute("DROP FUNCTION agreement_signatures_refuse_change()")
    op.drop_index("ix_agreement_signatures_user_id", table_name="agreement_signatures")
    op.drop_table("agreement_signatures")
    op.drop_index("ix_rental_agreements_owner_id", table_name="rental_agreements")
    op.drop_index("ix_rental_agreements_student_id", table_name="rental_agreements")
    op.drop_table("rental_agreements")
