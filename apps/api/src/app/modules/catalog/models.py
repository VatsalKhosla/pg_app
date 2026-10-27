"""Catalog tables (ARCHITECTURE §6, ADR 0021): owners, properties, room categories, rooms, beds and
amenities, and the verification visits that vouch for a property (ADR 0024).

Money is integer paise, and the database checks it as the domain does (CLAUDE.md rule 12). A
property's exact location and address line are for staff, and later for a student with a
scheduled visit or a confirmed booking; everyone else sees the display location (step 2.7).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AppendOnlyModel, Model
from app.core.ids import new_public_id
from app.modules.catalog.domain.listing import (
    HOUSE_RULES_MAX,
    SLUG_MAX_LENGTH,
    GenderPolicy,
    LicenceStatus,
    LocationPrecision,
    Meals,
    PropertyStatus,
    SocietyPermission,
    VerificationStatus,
)
from app.modules.catalog.domain.owners import GSTIN_PATTERN, KycStatus, OwnerStatus
from app.modules.catalog.domain.rooms import (
    HIGHEST_FLOOR,
    LOWEST_FLOOR,
    BedStatus,
    CategoryStatus,
    Occupancy,
)
from app.modules.catalog.domain.verification import VisitResult, VisitStatus

if TYPE_CHECKING:
    from collections.abc import Iterable
    from enum import StrEnum


def _one_of(column: str, values: Iterable[StrEnum]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def _slug_check() -> CheckConstraint:
    return CheckConstraint(
        f"slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) <= {SLUG_MAX_LENGTH}",
        name="slug",
    )


def _point() -> Geography:
    return Geography("POINT", srid=4326, spatial_index=False)


class Owner(Model):
    """A user account that lists PGs and pays the placement fee (ADR 0021)."""

    __tablename__ = "owners"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), unique=True)
    legal_name: Mapped[str] = mapped_column(Text)
    business_name: Mapped[str] = mapped_column(Text)
    gstin: Mapped[str | None] = mapped_column(Text)
    kyc_status: Mapped[str] = mapped_column(Text)
    # The gateway's linked account that split settlement pays (CLAUDE.md rule 10).
    payout_account_ref: Mapped[str | None] = mapped_column(Text)
    # The owner agreement accepted last (step 2.6).
    agreement_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(f"gstin ~ '^{GSTIN_PATTERN.pattern}$'", name="gstin"),
        CheckConstraint(_one_of("kyc_status", KycStatus), name="kyc_status"),
        CheckConstraint(_one_of("status", OwnerStatus), name="status"),
    )


class Property(Model):
    """A PG building, as listed."""

    __tablename__ = "properties"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("owners.id"))
    locality_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("localities.id"))
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    # Hidden like the exact location (CLAUDE.md rule 11).
    address_line: Mapped[str] = mapped_column(Text)
    location: Mapped[WKBElement] = mapped_column(_point())
    # The exact point moved 80 to 150 m, made once (domain/location.py).
    display_location: Mapped[WKBElement] = mapped_column(_point())
    location_precision: Mapped[str] = mapped_column(Text)
    gender_policy: Mapped[str] = mapped_column(Text)
    meals: Mapped[str] = mapped_column(Text)
    house_rules: Mapped[list[str]] = mapped_column(ARRAY(Text))
    verification_status: Mapped[str] = mapped_column(Text)
    licence_status: Mapped[str] = mapped_column(Text)
    licence_number: Mapped[str | None] = mapped_column(Text)
    society_permission: Mapped[str] = mapped_column(Text)
    instant_confirm: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(Text)
    # When it first went live; "newest" sorts by it.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _slug_check(),
        CheckConstraint(
            _one_of("location_precision", LocationPrecision), name="location_precision"
        ),
        CheckConstraint(_one_of("gender_policy", GenderPolicy), name="gender_policy"),
        CheckConstraint(_one_of("meals", Meals), name="meals"),
        CheckConstraint(
            _one_of("verification_status", VerificationStatus), name="verification_status"
        ),
        CheckConstraint(_one_of("licence_status", LicenceStatus), name="licence_status"),
        CheckConstraint(
            _one_of("society_permission", SocietyPermission), name="society_permission"
        ),
        CheckConstraint(_one_of("status", PropertyStatus), name="status"),
        CheckConstraint(f"cardinality(house_rules) <= {HOUSE_RULES_MAX}", name="house_rules"),
        Index("ix_properties_owner_id", "owner_id"),
        Index("ix_properties_locality_id", "locality_id"),
        Index("ix_properties_location", "location", postgresql_using="gist"),
        Index("ix_properties_display_location", "display_location", postgresql_using="gist"),
        Index(
            "ix_properties_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class RoomCategory(Model):
    """The unit students choose and prices are set for (ARCHITECTURE §6)."""

    __tablename__ = "room_categories"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"))
    occupancy: Mapped[str] = mapped_column(Text)
    ac: Mapped[bool] = mapped_column(Boolean)
    attached_bath: Mapped[bool] = mapped_column(Boolean)
    balcony: Mapped[bool] = mapped_column(Boolean)
    label: Mapped[str] = mapped_column(Text)
    # The listed rent per bed per month: the price when no rule applies, and the fee's basis.
    base_rent_paise: Mapped[int] = mapped_column(BigInteger)
    owner_min_rent_paise: Mapped[int | None] = mapped_column(BigInteger)
    owner_max_rent_paise: Mapped[int | None] = mapped_column(BigInteger)
    security_deposit_paise: Mapped[int] = mapped_column(BigInteger)
    # Typed in domain/charges.py; every amount in paise.
    mandatory_charges: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("occupancy", Occupancy), name="occupancy"),
        CheckConstraint(_one_of("status", CategoryStatus), name="status"),
        CheckConstraint("base_rent_paise > 0", name="base_rent"),
        CheckConstraint(
            "owner_min_rent_paise IS NULL"
            " OR (owner_min_rent_paise > 0 AND owner_min_rent_paise <= base_rent_paise)",
            name="owner_min_rent",
        ),
        CheckConstraint(
            "owner_max_rent_paise IS NULL OR owner_max_rent_paise >= base_rent_paise",
            name="owner_max_rent",
        ),
        CheckConstraint("security_deposit_paise >= 0", name="security_deposit"),
        CheckConstraint("jsonb_typeof(mandatory_charges) = 'array'", name="mandatory_charges"),
        Index("ix_room_categories_property_id", "property_id"),
    )


class Room(Model):
    __tablename__ = "rooms"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    room_category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("room_categories.id"))
    label: Mapped[str] = mapped_column(Text)
    floor: Mapped[int | None] = mapped_column(SmallInteger)

    __table_args__ = (
        # Also the index for the foreign key.
        UniqueConstraint("room_category_id", "label"),
        CheckConstraint(f"floor BETWEEN {LOWEST_FLOOR} AND {HIGHEST_FLOOR}", name="floor"),
    )


class Bed(Model):
    """The unit a booking takes; inventory allocations hold it for dates (step 5.1)."""

    __tablename__ = "beds"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    room_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("rooms.id"))
    label: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        # Also the index for the foreign key.
        UniqueConstraint("room_id", "label"),
        CheckConstraint(_one_of("status", BedStatus), name="status"),
    )


class Amenity(Model):
    __tablename__ = "amenities"

    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)

    __table_args__ = (_slug_check(),)


class PropertyAmenity(Model):
    __tablename__ = "property_amenities"

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE")
    )
    amenity_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("amenities.id"))

    __table_args__ = (
        # Also the index for the property's foreign key.
        UniqueConstraint("property_id", "amenity_id"),
        Index("ix_property_amenities_amenity_id", "amenity_id"),
    )


class PropertyMedia(Model):
    """A listing's photos and videos, in the order the page shows them; the first is the cover."""

    __tablename__ = "property_media"

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE")
    )
    media_asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("media_assets.id"))
    position: Mapped[int] = mapped_column(SmallInteger)

    __table_args__ = (
        # Also the index for the property's foreign key.
        UniqueConstraint("property_id", "media_asset_id"),
        CheckConstraint("position >= 0", name="position"),
        Index("ix_property_media_media_asset_id", "media_asset_id"),
    )


class VerificationVisit(Model):
    """A field agent's visit to vouch for a property: scheduled by ops for one agent, then the
    report the agent submits on site, or cancelled (ADR 0024)."""

    __tablename__ = "verification_visits"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"))
    agent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    scheduled_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    # The property's verification status before the visit was booked, which a cancellation puts
    # back.
    status_before: Mapped[str] = mapped_column(Text)
    # The report: when it came in (the server's clock), where the agent's phone said they were,
    # and how far that was from the property's pin at the time.
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[WKBElement | None] = mapped_column(_point(), nullable=True)
    position_accuracy_m: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[int | None] = mapped_column(Integer)
    checklist: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, server_default="")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("status", VisitStatus), name="status"),
        CheckConstraint(_one_of("status_before", VerificationStatus), name="status_before"),
        CheckConstraint(_one_of("result", VisitResult), name="result"),
        # A submitted visit has the whole report, and only a submitted one has any of it.
        CheckConstraint(
            "(status = 'submitted') = (submitted_at IS NOT NULL AND position IS NOT NULL"
            " AND position_accuracy_m IS NOT NULL AND distance_m IS NOT NULL"
            " AND checklist IS NOT NULL AND result IS NOT NULL)",
            name="report",
        ),
        CheckConstraint("(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="cancelled"),
        CheckConstraint("result IS DISTINCT FROM 'failed' OR notes <> ''", name="failed_notes"),
        CheckConstraint("position_accuracy_m >= 0 AND distance_m >= 0", name="distances"),
        # One visit booked at a time for a property.
        Index(
            "uq_verification_visits_property_id_scheduled",
            "property_id",
            unique=True,
            postgresql_where=text("status = 'scheduled'"),
        ),
        Index("ix_verification_visits_property_id", "property_id"),
        Index(
            "ix_verification_visits_agent_id_status_scheduled_for",
            "agent_id",
            "status",
            "scheduled_for",
        ),
        Index("ix_verification_visits_scheduled_by", "scheduled_by"),
    )


class VerificationPhoto(Model):
    """A report's photos, in the order the agent took them: private evidence (ADR 0024)."""

    __tablename__ = "verification_photos"

    visit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verification_visits.id", ondelete="CASCADE")
    )
    media_asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("media_assets.id"))
    position: Mapped[int] = mapped_column(SmallInteger)

    __table_args__ = (
        # Also the index for the visit's foreign key.
        UniqueConstraint("visit_id", "media_asset_id"),
        CheckConstraint("position >= 0", name="position"),
        Index("ix_verification_photos_media_asset_id", "media_asset_id"),
    )


class OwnerAgreement(AppendOnlyModel):
    """An owner's click-wrap acceptance of one version of the owner agreement (ADR 0025): what was
    accepted (the version and the SHA-256 of its exact text), when, from where. The database
    refuses to change or delete one: they're the evidence of what the owner agreed to."""

    __tablename__ = "owner_agreements"

    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("owners.id"))
    version: Mapped[str] = mapped_column(Text)
    document_sha256: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_ip: Mapped[str] = mapped_column(Text)
    accepted_user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("version ~ '^[a-z0-9][a-z0-9.-]{0,63}$'", name="version"),
        CheckConstraint("document_sha256 ~ '^[0-9a-f]{64}$'", name="document_sha256"),
        Index("ix_owner_agreements_owner_id_accepted_at", "owner_id", "accepted_at"),
    )
