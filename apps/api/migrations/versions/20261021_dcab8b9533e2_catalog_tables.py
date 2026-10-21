"""catalog tables

Revision ID: dcab8b9533e2
Revises: f62436765bf0
Create Date: 2026-10-21 21:46:14.109652

The catalog of step 2.2 (ARCHITECTURE §6, ADR 0021):
- owners, properties and their amenities;
- room categories (the unit that is sold and priced), their rooms, and the beds in each room.

Money is bigint paise, checked here as in the domain:
- the base rent is positive;
- an owner's minimum and maximum, when set, bound it;
- the deposit isn't negative.

Each property's exact location and display location get GiST indexes, its name a trigram index,
and every foreign key a btree index (the unique constraints that lead with one serve as theirs).
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "dcab8b9533e2"
down_revision: str | Sequence[str] | None = "f62436765bf0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SLUG_CHECK = "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) <= 80"


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _id() -> sa.Column[int]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _one_of(table: str, column: str, values: Sequence[str]) -> sa.CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({allowed})", name=op.f(f"ck_{table}_{column}"))


def upgrade() -> None:
    op.create_table(
        "owners",
        _id(),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("business_name", sa.Text(), nullable=False),
        sa.Column("gstin", sa.Text(), nullable=True),
        sa.Column("kyc_status", sa.Text(), nullable=False),
        sa.Column("payout_account_ref", sa.Text(), nullable=True),
        sa.Column("agreement_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'",
            name=op.f("ck_owners_gstin"),
        ),
        _one_of("owners", "kyc_status", ("not_started", "pending", "verified", "rejected")),
        _one_of("owners", "status", ("active", "suspended")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_owners_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owners")),
        sa.UniqueConstraint("public_id", name=op.f("uq_owners_public_id")),
        sa.UniqueConstraint("user_id", name=op.f("uq_owners_user_id")),
    )
    op.create_table(
        "properties",
        _id(),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("locality_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("address_line", sa.Text(), nullable=False),
        sa.Column("location", Geography("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column(
            "display_location",
            Geography("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("location_precision", sa.Text(), nullable=False),
        sa.Column("gender_policy", sa.Text(), nullable=False),
        sa.Column("meals", sa.Text(), nullable=False),
        sa.Column("house_rules", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("verification_status", sa.Text(), nullable=False),
        sa.Column("licence_status", sa.Text(), nullable=False),
        sa.Column("licence_number", sa.Text(), nullable=True),
        sa.Column("society_permission", sa.Text(), nullable=False),
        sa.Column("instant_confirm", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(SLUG_CHECK, name=op.f("ck_properties_slug")),
        _one_of("properties", "location_precision", ("exact", "approximate")),
        _one_of("properties", "gender_policy", ("boys", "girls", "coed")),
        _one_of("properties", "meals", ("none", "breakfast", "two", "three", "four")),
        _one_of(
            "properties",
            "verification_status",
            ("unverified", "scheduled", "verified", "rejected", "suspended"),
        ),
        _one_of("properties", "licence_status", ("unknown", "applied", "licensed", "not_required")),
        _one_of("properties", "society_permission", ("n/a", "on_file", "missing")),
        _one_of("properties", "status", ("draft", "published", "paused", "delisted")),
        sa.CheckConstraint(
            "cardinality(house_rules) <= 30", name=op.f("ck_properties_house_rules")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owners.id"], name=op.f("fk_properties_owner_id_owners")
        ),
        sa.ForeignKeyConstraint(
            ["locality_id"], ["localities.id"], name=op.f("fk_properties_locality_id_localities")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_properties")),
        sa.UniqueConstraint("public_id", name=op.f("uq_properties_public_id")),
        sa.UniqueConstraint("slug", name=op.f("uq_properties_slug")),
    )
    op.create_index("ix_properties_owner_id", "properties", ["owner_id"])
    op.create_index("ix_properties_locality_id", "properties", ["locality_id"])
    op.create_index("ix_properties_location", "properties", ["location"], postgresql_using="gist")
    op.create_index(
        "ix_properties_display_location",
        "properties",
        ["display_location"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_properties_name_trgm",
        "properties",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_table(
        "room_categories",
        _id(),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("occupancy", sa.Text(), nullable=False),
        sa.Column("ac", sa.Boolean(), nullable=False),
        sa.Column("attached_bath", sa.Boolean(), nullable=False),
        sa.Column("balcony", sa.Boolean(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("base_rent_paise", sa.BigInteger(), nullable=False),
        sa.Column("owner_min_rent_paise", sa.BigInteger(), nullable=True),
        sa.Column("owner_max_rent_paise", sa.BigInteger(), nullable=True),
        sa.Column("security_deposit_paise", sa.BigInteger(), nullable=False),
        sa.Column("mandatory_charges", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        *_timestamps(),
        _one_of("room_categories", "occupancy", ("single", "double", "triple", "quad")),
        _one_of("room_categories", "status", ("active", "inactive")),
        sa.CheckConstraint("base_rent_paise > 0", name=op.f("ck_room_categories_base_rent")),
        sa.CheckConstraint(
            "owner_min_rent_paise IS NULL"
            " OR (owner_min_rent_paise > 0 AND owner_min_rent_paise <= base_rent_paise)",
            name=op.f("ck_room_categories_owner_min_rent"),
        ),
        sa.CheckConstraint(
            "owner_max_rent_paise IS NULL OR owner_max_rent_paise >= base_rent_paise",
            name=op.f("ck_room_categories_owner_max_rent"),
        ),
        sa.CheckConstraint(
            "security_deposit_paise >= 0", name=op.f("ck_room_categories_security_deposit")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(mandatory_charges) = 'array'",
            name=op.f("ck_room_categories_mandatory_charges"),
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_room_categories_property_id_properties"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_room_categories")),
        sa.UniqueConstraint("public_id", name=op.f("uq_room_categories_public_id")),
    )
    op.create_index("ix_room_categories_property_id", "room_categories", ["property_id"])
    op.create_table(
        "rooms",
        _id(),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("room_category_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("floor", sa.SmallInteger(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("floor BETWEEN -3 AND 60", name=op.f("ck_rooms_floor")),
        sa.ForeignKeyConstraint(
            ["room_category_id"],
            ["room_categories.id"],
            name=op.f("fk_rooms_room_category_id_room_categories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rooms")),
        sa.UniqueConstraint("public_id", name=op.f("uq_rooms_public_id")),
        sa.UniqueConstraint(
            "room_category_id", "label", name=op.f("uq_rooms_room_category_id_label")
        ),
    )
    op.create_table(
        "beds",
        _id(),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        *_timestamps(),
        _one_of("beds", "status", ("active", "inactive")),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], name=op.f("fk_beds_room_id_rooms")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_beds")),
        sa.UniqueConstraint("public_id", name=op.f("uq_beds_public_id")),
        sa.UniqueConstraint("room_id", "label", name=op.f("uq_beds_room_id_label")),
    )
    op.create_table(
        "amenities",
        _id(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(SLUG_CHECK, name=op.f("ck_amenities_slug")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_amenities")),
        sa.UniqueConstraint("slug", name=op.f("uq_amenities_slug")),
    )
    op.create_table(
        "property_amenities",
        _id(),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("amenity_id", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_property_amenities_property_id_properties"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["amenity_id"],
            ["amenities.id"],
            name=op.f("fk_property_amenities_amenity_id_amenities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_amenities")),
        sa.UniqueConstraint(
            "property_id", "amenity_id", name=op.f("uq_property_amenities_property_id_amenity_id")
        ),
    )
    op.create_index("ix_property_amenities_amenity_id", "property_amenities", ["amenity_id"])


def downgrade() -> None:
    op.drop_table("property_amenities")
    op.drop_table("amenities")
    op.drop_table("beds")
    op.drop_table("rooms")
    op.drop_table("room_categories")
    op.drop_table("properties")
    op.drop_table("owners")
