"""Pricing's policy tables (ARCHITECTURE §6; step 4.1, ADR 0036). Each row is one version of a
policy, in force from ``effective_from`` until ``effective_to`` (open while it's the current one).
Versions are never edited: a change ends the current one and adds the next, and the exclusion
constraints keep any two from overlapping, so at any moment exactly one is in force.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy import text as sql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.ids import new_public_id
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.pricing.domain.engine import LABEL_MAX_LENGTH, RuleKind
from app.modules.pricing.domain.policies import (
    MAX_RENT,
    NOTE_MAX_LENGTH,
    REFERENCE_MAX_LENGTH,
    BandSource,
    FeeBasis,
    GstMode,
    LateCancelPolicy,
)
from app.modules.pricing.domain.rule_sets import RuleSetStatus

if TYPE_CHECKING:
    from enum import StrEnum

# The span a version is in force for, as the exclusion constraints compare it.
IN_FORCE: Final = "tstzrange(effective_from, effective_to)"


def _one_of(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class PolicyVersion(Model):
    """What every policy version has: when it's in force, who made it, and why."""

    __abstract__ = True

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The admin who made it; none for the seeded defaults.
    changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str] = mapped_column(Text, server_default="")


def _version_checks(table: str) -> tuple[object, ...]:
    return (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="effective_order"
        ),
        CheckConstraint(f"char_length(note) <= {NOTE_MAX_LENGTH}", name="note_length"),
        ExcludeConstraint((sql(IN_FORCE), "&&"), using="gist", name=f"ex_{table}_in_force"),
    )


class FeePolicyVersion(PolicyVersion):
    """The owner's placement fee (rules 2 and 3)."""

    __tablename__ = "fee_policies"

    rate_bps: Mapped[int] = mapped_column(Integer)
    basis: Mapped[str] = mapped_column(Text)
    gst_rate_bps: Mapped[int] = mapped_column(Integer)
    gst_mode: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("rate_bps BETWEEN 0 AND 10000", name="rate"),
        CheckConstraint("gst_rate_bps BETWEEN 0 AND 10000", name="gst_rate"),
        CheckConstraint(_one_of("basis", FeeBasis), name="basis"),
        CheckConstraint(_one_of("gst_mode", GstMode), name="gst_mode"),
        *_version_checks("fee_policies"),
    )


class BookingPolicyVersion(PolicyVersion):
    """The terms a booking runs on (rules 8 and 9)."""

    __tablename__ = "booking_policies"

    token_paise: Mapped[int] = mapped_column(BigInteger)
    hold_minutes: Mapped[int] = mapped_column(Integer)
    free_cancel_days: Mapped[int] = mapped_column(Integer)
    check_window_hours: Mapped[int] = mapped_column(Integer)
    confirm_deadline_hours: Mapped[int] = mapped_column(Integer)
    no_show_days: Mapped[int] = mapped_column(Integer)
    late_cancel_policy: Mapped[str] = mapped_column(Text)
    max_active_holds_per_user: Mapped[int] = mapped_column(Integer)
    max_advance_days: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        # Rule 8: never above ₹2,000.
        CheckConstraint("token_paise BETWEEN 100000 AND 200000", name="token"),
        CheckConstraint(
            "hold_minutes > 0 AND free_cancel_days >= 0 AND check_window_hours > 0"
            " AND confirm_deadline_hours > 0 AND no_show_days > 0"
            " AND max_active_holds_per_user > 0 AND max_advance_days > 0",
            name="terms",
        ),
        CheckConstraint(_one_of("late_cancel_policy", LateCancelPolicy), name="late_cancel"),
        *_version_checks("booking_policies"),
    )


class PricingCapsVersion(PolicyVersion):
    """How far dynamic prices may move from the listed rent, and the step they round to (rule 6)."""

    __tablename__ = "pricing_caps"

    max_premium_bps: Mapped[int] = mapped_column(Integer)
    max_discount_bps: Mapped[int] = mapped_column(Integer)
    rounding_step_paise: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint("max_premium_bps BETWEEN 0 AND 10000", name="premium"),
        CheckConstraint("max_discount_bps BETWEEN 0 AND 9000", name="discount"),
        CheckConstraint(
            "rounding_step_paise BETWEEN 100 AND 100000 AND rounding_step_paise % 100 = 0",
            name="rounding_step",
        ),
        *_version_checks("pricing_caps"),
    )


class RentBand(PolicyVersion):
    """The rents a locality allows for one occupancy (rule 6): an official band once the
    authorities set them, or an internal one ops set from the market. None is seeded."""

    __tablename__ = "rent_bands"

    locality_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("localities.id"))
    occupancy: Mapped[str] = mapped_column(Text)
    min_rent_paise: Mapped[int] = mapped_column(BigInteger)
    max_rent_paise: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(Text)
    reference: Mapped[str] = mapped_column(Text, server_default="")

    __table_args__ = (
        CheckConstraint(
            f"min_rent_paise > 0 AND min_rent_paise <= max_rent_paise"
            f" AND max_rent_paise <= {MAX_RENT}",
            name="rents",
        ),
        CheckConstraint(_one_of("occupancy", Occupancy), name="occupancy"),
        CheckConstraint(_one_of("source", BandSource), name="source"),
        CheckConstraint(
            f"char_length(reference) <= {REFERENCE_MAX_LENGTH}"
            " AND (source <> 'official' OR reference <> '')",
            name="reference",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="effective_order"
        ),
        CheckConstraint(f"char_length(note) <= {NOTE_MAX_LENGTH}", name="note_length"),
        # One band in force at a time for each locality and occupancy.
        ExcludeConstraint(
            ("locality_id", "="),
            ("occupancy", "="),
            (sql(IN_FORCE), "&&"),
            using="gist",
            name="ex_rent_bands_in_force",
        ),
        Index("ix_rent_bands_locality_id", "locality_id"),
    )


class PricingRuleSet(Model):
    """One version of a PG's pricing rules (ADR 0038): a draft while it's edited, then active,
    then archived. Only a draft's rules may change; the database refuses anything else."""

    __tablename__ = "pricing_rule_sets"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why it was activated, for the history.
    note: Mapped[str] = mapped_column(Text, server_default="")

    __table_args__ = (
        CheckConstraint(_one_of("status", RuleSetStatus), name="status"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("(status = 'draft') = (activated_at IS NULL)", name="activated"),
        CheckConstraint("(status = 'archived') = (archived_at IS NOT NULL)", name="archived"),
        CheckConstraint(f"char_length(note) <= {NOTE_MAX_LENGTH}", name="note_length"),
        Index("uq_pricing_rule_sets_property_id_version", "property_id", "version", unique=True),
        # One set in force, and one being edited, per PG.
        Index(
            "uq_pricing_rule_sets_property_id_active",
            "property_id",
            unique=True,
            postgresql_where=sql("status = 'active'"),
        ),
        Index(
            "uq_pricing_rule_sets_property_id_draft",
            "property_id",
            unique=True,
            postgresql_where=sql("status = 'draft'"),
        ),
    )


class PricingRuleRow(Model):
    """One rule of a set, in the set's order. Its parameters are JSON, as the domain writes them
    (pricing/domain/rule_sets.py)."""

    __tablename__ = "pricing_rules"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    rule_set_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pricing_rule_sets.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    # The room categories it's for; NULL for all of the PG's.
    room_category_ids: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    params: Mapped[dict[str, object]] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=sql("true"))

    __table_args__ = (
        CheckConstraint(_one_of("kind", RuleKind), name="kind"),
        CheckConstraint(
            f"char_length(btrim(label)) BETWEEN 1 AND {LABEL_MAX_LENGTH}", name="label"
        ),
        CheckConstraint("position >= 0", name="position"),
        Index("uq_pricing_rules_rule_set_id_position", "rule_set_id", "position", unique=True),
    )
