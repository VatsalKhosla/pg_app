"""The agreements module's tables (ADR 0070): a booking's rent agreement, the signatures on it, the
codes signers confirm with, and the tenant's police verification.

The database keeps the record honest, whatever the code above it does:
- an agreement's ``text_sha256`` is the SHA-256 of its ``text`` (a check);
- a signature names the agreement's text by that hash, through a foreign key to the pair, so a
  text somebody has signed can never change, and both signatures are of the same words;
- each side signs once, and signatures can't be changed or deleted (a trigger);
- police-verification details are stored only sealed (app/core/sealing.py), never readable here.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AppendOnlyModel, Model
from app.core.ids import new_public_id
from app.modules.agreements.domain.agreements import TYPED_NAME_MAX, AgreementStatus, Signer
from app.modules.agreements.domain.verification import PoliceVerificationStatus

if TYPE_CHECKING:
    from enum import StrEnum

# A text's SHA-256 as Postgres works it out: what the check compares ``text_sha256`` with.
TEXT_HASH: Final = "encode(sha256(convert_to(text, 'UTF8')), 'hex')"


def _one_of(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class RentalAgreement(Model):
    """A booking's leave-and-licence agreement between its student and its PG's owner.

    Its text follows the booking's facts and the template in force until somebody signs; from the
    first signature on, it is fixed. The parties are copied from the booking when it's made.
    """

    __tablename__ = "rental_agreements"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bookings.id"), unique=True)
    # The licensee's account, and the licensor's business record.
    student_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("owners.id"))
    status: Mapped[str] = mapped_column(Text)
    template_version: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(Text)
    # When the second side signed.
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the booking reached its end (early or after the stay), whether or not this was signed.
    booking_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_one_of("status", AgreementStatus), name="status"),
        CheckConstraint(f"text_sha256 = {TEXT_HASH}", name="text_sha256"),
        CheckConstraint("template_version ~ '^[a-z0-9][a-z0-9.-]{0,63}$'", name="template_version"),
        CheckConstraint("(status = 'signed') = (signed_at IS NOT NULL)", name="signed"),
        CheckConstraint("(status = 'void') = (voided_at IS NOT NULL)", name="void"),
        CheckConstraint("status <> 'void' OR booking_ended_at IS NOT NULL", name="void_ended"),
        # What signatures refer to: this agreement, as it read when they were made.
        UniqueConstraint("id", "text_sha256", name="uq_rental_agreements_id_text_sha256"),
        Index("ix_rental_agreements_student_id", "student_id"),
        Index("ix_rental_agreements_owner_id", "owner_id"),
    )


class AgreementSignature(AppendOnlyModel):
    """One side's signature: who, as whom, with what typed name, when, from where, and the exact
    text by its hash. Never changed or deleted (a trigger refuses)."""

    __tablename__ = "agreement_signatures"

    agreement_id: Mapped[int] = mapped_column(BigInteger)
    text_sha256: Mapped[str] = mapped_column(Text)
    template_version: Mapped[str] = mapped_column(Text)
    signer: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    typed_name: Mapped[str] = mapped_column(Text)
    # From the injectable clock, when the code was accepted.
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        ForeignKeyConstraint(
            ["agreement_id", "text_sha256"],
            ["rental_agreements.id", "rental_agreements.text_sha256"],
            name="fk_agreement_signatures_agreement_text",
        ),
        UniqueConstraint("agreement_id", "signer"),
        CheckConstraint(_one_of("signer", Signer), name="signer"),
        CheckConstraint(
            f"char_length(typed_name) BETWEEN 2 AND {TYPED_NAME_MAX}", name="typed_name"
        ),
        CheckConstraint("text_sha256 ~ '^[0-9a-f]{64}$'", name="text_sha256"),
        Index("ix_agreement_signatures_user_id", "user_id"),
    )


class SigningCode(Model):
    """A one-time code one side asked for to sign one agreement. The code is kept only as an HMAC
    under SECRET_KEY, bound to this row, so a leaked table reveals no code."""

    __tablename__ = "agreement_signing_codes"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    agreement_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("rental_agreements.id"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    signer: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A newer code for the same signer and agreement replaced this one.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("signer", Signer), name="signer"),
        CheckConstraint("attempts >= 0", name="attempts"),
        Index(
            "ix_agreement_signing_codes_agreement_user",
            "agreement_id",
            "user_id",
            "requested_at",
        ),
        Index("ix_agreement_signing_codes_user_id", "user_id"),
        # The retention rule's scan.
        Index("ix_agreement_signing_codes_requested_at", "requested_at"),
    )


class TenantVerification(Model):
    """The tenant's police verification for one agreement. The student's details are sealed;
    nothing else here is personal."""

    __tablename__ = "tenant_verifications"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    agreement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rental_agreements.id"), unique=True
    )
    status: Mapped[str] = mapped_column(Text)
    # The details, sealed for this row; None once erased by the retention schedule.
    details_sealed: Mapped[str | None] = mapped_column(Text)
    details_submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The owner's upload of the portal's acknowledgement, a private document.
    acknowledgement_media_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("media_assets.id"), unique=True
    )
    # The portal's acknowledgement or registration number, if the owner gave it.
    police_reference: Mapped[str | None] = mapped_column(Text)
    submitted_to_police_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # A row exists once the student has given their details.
        CheckConstraint(
            _one_of("status", PoliceVerificationStatus) + " AND status <> 'not_started'",
            name="status",
        ),
        CheckConstraint("(details_sealed IS NULL) = (erased_at IS NOT NULL)", name="erased"),
        CheckConstraint(
            "(status IN ('submitted_to_police', 'verified'))"
            " = (submitted_to_police_at IS NOT NULL AND acknowledgement_media_id IS NOT NULL"
            " AND submitted_by IS NOT NULL)",
            name="submitted",
        ),
        CheckConstraint(
            "(status = 'verified') = (verified_at IS NOT NULL AND verified_by IS NOT NULL)",
            name="verified",
        ),
        CheckConstraint(
            "police_reference IS NULL OR char_length(police_reference) BETWEEN 1 AND 60",
            name="police_reference",
        ),
        Index("ix_tenant_verifications_submitted_by", "submitted_by"),
        Index("ix_tenant_verifications_verified_by", "verified_by"),
    )
