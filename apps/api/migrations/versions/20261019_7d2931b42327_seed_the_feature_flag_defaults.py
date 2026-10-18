"""seed the feature flag defaults

Revision ID: 7d2931b42327
Revises: df8655f00b57
Create Date: 2026-10-19 00:09:13.000000

A data migration, kept apart from the schema migration (backend rules). The values are the
defaults PRODUCT_CONTEXT §9 records, written out here rather than imported from app.core.flags,
so this migration means the same thing however that module changes later.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7d2931b42327"
down_revision: str | Sequence[str] | None = "df8655f00b57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FLAGS: list[tuple[str, bool | str, str]] = [
    (
        "remote_booking_enabled",
        False,
        "Students can reserve a bed without a visit first (season one is visit-first).",
    ),
    (
        "token_mode",
        "payment",
        "How the token is taken: a normal payment held until move-in, or a UPI one-time mandate"
        " (only once Razorpay enables mandates for the account).",
    ),
    (
        "rent_via_app_enabled",
        False,
        "The rest of the first month's rent can be paid through the app (Phase 9).",
    ),
    (
        "hide_owner_contact",
        True,
        "Owner phone and exact address stay hidden until a visit is scheduled or a booking is"
        " confirmed (pending legal advice).",
    ),
    (
        "instant_confirm_default",
        False,
        "New properties confirm bookings instantly instead of waiting for the owner.",
    ),
    ("reviews_enabled", False, "Verified-resident reviews (Phase 9)."),
    ("whatsapp_enabled", False, "Notifications on WhatsApp (Phase 9)."),
    (
        "price_suggestions_enabled",
        False,
        "Price suggestions for owners from demand data (Phase 9).",
    ),
]

feature_flags = sa.table(
    "feature_flags",
    sa.column("key", sa.Text()),
    sa.column("value", postgresql.JSONB()),
    sa.column("description", sa.Text()),
)


def upgrade() -> None:
    op.bulk_insert(
        feature_flags,
        [
            {"key": key, "value": value, "description": description}
            for key, value, description in FLAGS
        ],
    )


def downgrade() -> None:
    op.execute(feature_flags.delete().where(feature_flags.c.key.in_([key for key, _, _ in FLAGS])))
