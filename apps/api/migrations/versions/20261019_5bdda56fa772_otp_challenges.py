"""otp challenges

Revision ID: 5bdda56fa772
Revises: 1ff9609ff665
Create Date: 2026-10-19 16:14:06.457121

Sign-in codes of step 1.2 (ARCHITECTURE §6, §12). ``code_hash`` is an HMAC under SECRET_KEY bound
to the challenge; the code itself is never stored. The index serves the per-phone cooldown check.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "5bdda56fa772"
down_revision: str | Sequence[str] | None = "1ff9609ff665"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("phone_e164", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("purpose IN ('sign_in')", name="purpose"),
        sa.CheckConstraint("attempts >= 0", name="attempts"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_otp_challenges")),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_otp_challenges_phone_e164_requested_at",
        "otp_challenges",
        ["phone_e164", "requested_at"],
    )


def downgrade() -> None:
    op.drop_table("otp_challenges")
