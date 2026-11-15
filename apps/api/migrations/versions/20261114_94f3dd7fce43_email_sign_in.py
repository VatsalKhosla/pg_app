"""email sign-in

Revision ID: 94f3dd7fce43
Revises: c6f2a8e4b9d1
Create Date: 2026-11-14 12:00:00.000000

Sign-in by email (ADR 0068): an account has a phone, an email address or both, and a sign-in code
goes to one of the two. Expand only: every row already has a phone.

Going back needs every account to have a phone again: it stops, changing nothing, while an account
without one exists. Codes sent to an address are dropped (they last minutes).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "94f3dd7fce43"
down_revision: str | Sequence[str] | None = "c6f2a8e4b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "phone_e164", existing_type=sa.Text(), nullable=True)
    op.create_check_constraint(
        op.f("ck_users_contact"), "users", "phone_e164 IS NOT NULL OR email IS NOT NULL"
    )

    op.add_column("otp_challenges", sa.Column("email", postgresql.CITEXT(), nullable=True))
    op.alter_column("otp_challenges", "phone_e164", existing_type=sa.Text(), nullable=True)
    op.create_check_constraint(
        op.f("ck_otp_challenges_destination"),
        "otp_challenges",
        "num_nonnulls(phone_e164, email) = 1",
    )
    op.create_index(
        op.f("ix_otp_challenges_email_requested_at"),
        "otp_challenges",
        ["email", "requested_at"],
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM users WHERE phone_e164 IS NULL) THEN
                RAISE EXCEPTION 'accounts without a phone exist; they need one before going back';
            END IF;
        END
        $$
        """
    )
    op.execute("DELETE FROM otp_challenges WHERE phone_e164 IS NULL")
    op.drop_index(op.f("ix_otp_challenges_email_requested_at"), table_name="otp_challenges")
    op.drop_constraint(op.f("ck_otp_challenges_destination"), "otp_challenges", type_="check")
    op.alter_column("otp_challenges", "phone_e164", existing_type=sa.Text(), nullable=False)
    op.drop_column("otp_challenges", "email")

    op.drop_constraint(op.f("ck_users_contact"), "users", type_="check")
    op.alter_column("users", "phone_e164", existing_type=sa.Text(), nullable=False)
