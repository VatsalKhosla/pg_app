"""fill board timers

Revision ID: 3f8a6b5d2c71
Revises: 7d1c2e4b9a10
Create Date: 2026-11-04 18:01:00.000000

Rows from before the board's timers (ADR 0054): a token came in when the booking's history says
it reached TOKEN_SECURED, and a dispute opened when its row was made.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "3f8a6b5d2c71"
down_revision: str | Sequence[str] | None = "7d1c2e4b9a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE bookings
        SET token_secured_at = reached.at
        FROM (
            SELECT booking_id, max(created_at) AS at
            FROM booking_events
            WHERE to_status = 'token_secured'
            GROUP BY booking_id
        ) AS reached
        WHERE reached.booking_id = bookings.id AND bookings.token_secured_at IS NULL
        """
    )
    op.execute("UPDATE disputes SET opened_at = created_at")


def downgrade() -> None:
    # The columns go with the previous migration; the rows hold nothing else to put back.
    pass
