"""property price summaries

Revision ID: 1aec74b70c66
Revises: 3fda18ae2d09
Create Date: 2026-10-27 15:08:15.409985

Price summaries (step 3.1, ADR 0027): each room category's rent range for each month from this
one, which search filters and sorts on and the map shows. The search module owns the table and
refreshes it from the catalog's events; it points at the catalog's rows, which are never
deleted.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "1aec74b70c66"
down_revision: str | Sequence[str] | None = "3fda18ae2d09"
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
        "property_price_summaries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("room_category_id", sa.BigInteger(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("min_rent_paise", sa.BigInteger(), nullable=False),
        sa.Column("max_rent_paise", sa.BigInteger(), nullable=False),
        sa.Column("available_beds", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "extract(day from month) = 1", name=op.f("ck_property_price_summaries_month")
        ),
        sa.CheckConstraint(
            "0 < min_rent_paise AND min_rent_paise <= max_rent_paise",
            name=op.f("ck_property_price_summaries_rents"),
        ),
        sa.CheckConstraint(
            "available_beds >= 0", name=op.f("ck_property_price_summaries_available_beds")
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_property_price_summaries_property_id_properties"),
        ),
        sa.ForeignKeyConstraint(
            ["room_category_id"],
            ["room_categories.id"],
            name=op.f("fk_property_price_summaries_room_category_id_room_categories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_price_summaries")),
        sa.UniqueConstraint(
            "room_category_id",
            "month",
            name=op.f("uq_property_price_summaries_room_category_id_month"),
        ),
    )
    op.create_index(
        "ix_property_price_summaries_property_id", "property_price_summaries", ["property_id"]
    )
    op.create_index(
        "ix_property_price_summaries_month_min_rent_paise",
        "property_price_summaries",
        ["month", "min_rent_paise"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_property_price_summaries_month_min_rent_paise", table_name="property_price_summaries"
    )
    op.drop_index("ix_property_price_summaries_property_id", table_name="property_price_summaries")
    op.drop_table("property_price_summaries")
