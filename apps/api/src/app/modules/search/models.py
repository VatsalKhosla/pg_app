"""The search module's tables (ARCHITECTURE §6): a read model it refreshes from the catalog's
events, never written by anyone else."""

import uuid
from datetime import date, datetime

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class PropertyPriceSummary(Model):
    """A room category's rent range for one month (step 3.1, ADR 0027): what search filters and
    sorts on by budget, and the map's price pins show."""

    __tablename__ = "property_price_summaries"

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"))
    room_category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("room_categories.id"))
    # The month's first day.
    month: Mapped[date] = mapped_column(Date)
    min_rent_paise: Mapped[int] = mapped_column(BigInteger)
    max_rent_paise: Mapped[int] = mapped_column(BigInteger)
    available_beds: Mapped[int] = mapped_column(Integer)
    # The category's features, which search filters by (step 3.2).
    occupancy: Mapped[str] = mapped_column(Text)
    ac: Mapped[bool] = mapped_column(Boolean)
    attached_bath: Mapped[bool] = mapped_column(Boolean)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("room_category_id", "month"),
        CheckConstraint("occupancy IN ('single', 'double', 'triple', 'quad')", name="occupancy"),
        CheckConstraint("extract(day from month) = 1", name="month"),
        CheckConstraint("0 < min_rent_paise AND min_rent_paise <= max_rent_paise", name="rents"),
        CheckConstraint("available_beds >= 0", name="available_beds"),
        # Replacing a listing's summaries, and search's lookup of its month.
        Index("ix_property_price_summaries_property_id_month", "property_id", "month"),
    )


class SearchListing(Model):
    """A listing the public can find, as search filters, sorts and shows it (step 3.2, ADR
    0028): public details only, kept from the catalog's events. Not published, or failed or
    suspended, means no row; whether only verified ones show is decided at search time."""

    __tablename__ = "search_listings"

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), unique=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    slug: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    locality_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("localities.id"))
    locality_slug: Mapped[str] = mapped_column(Text)
    locality_name: Mapped[str] = mapped_column(Text)
    # The display point (ADR 0021): search never holds the exact one.
    display_location: Mapped[WKBElement] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False)
    )
    gender_policy: Mapped[str] = mapped_column(Text)
    meals: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean)
    licensed: Mapped[bool] = mapped_column(Boolean)
    amenities: Mapped[list[str]] = mapped_column(ARRAY(Text))
    # The first few photos and videos, in page order: the card's cover is the first one ready.
    media_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # What text search matches: words (full text) and near misses (trigrams).
    search_text: Mapped[str] = mapped_column(
        Text, Computed("name || ' '::text || locality_name", persisted=True)
    )
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple'::regconfig, name || ' '::text || locality_name)", persisted=True
        ),
    )

    __table_args__ = (
        Index("ix_search_listings_display_location", "display_location", postgresql_using="gist"),
        Index("ix_search_listings_locality_id", "locality_id"),
        Index("ix_search_listings_amenities", "amenities", postgresql_using="gin"),
        Index("ix_search_listings_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_search_listings_search_text",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        Index("ix_search_listings_published_at", "published_at"),
    )
