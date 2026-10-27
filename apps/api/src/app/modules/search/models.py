"""The search module's tables (ARCHITECTURE §6): a read model it refreshes from the catalog's
events, never written by anyone else."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
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
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("room_category_id", "month"),
        CheckConstraint("extract(day from month) = 1", name="month"),
        CheckConstraint("0 < min_rent_paise AND min_rent_paise <= max_rent_paise", name="rents"),
        CheckConstraint("available_beds >= 0", name="available_beds"),
        Index("ix_property_price_summaries_property_id", "property_id"),
        # Search's budget filter and price sort, within a month.
        Index("ix_property_price_summaries_month_min_rent_paise", "month", "min_rent_paise"),
    )
