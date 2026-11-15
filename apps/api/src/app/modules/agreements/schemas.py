"""Request and response bodies of rent agreements and police verification (ADR 0070)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints
from pydantic_core import PydanticCustomError

from app.core.schemas import ApiModel
from app.modules.agreements.domain.agreements import (
    TYPED_NAME_MAX,
    TYPED_NAME_MIN,
    AgreementStatus,
    Signer,
    typed_name,
)
from app.modules.agreements.domain.codes import CODE_DIGITS
from app.modules.agreements.domain.verification import (
    MAX_REFERENCES,
    IdType,
    Occupation,
    PoliceVerificationStatus,
    holds_aadhaar_like_number,
)
from app.modules.identity.domain.phones import normalize_indian_mobile
from app.modules.identity.domain.profile import Gender


def _no_aadhaar_number(value: str) -> str:
    if holds_aadhaar_like_number(value):
        raise PydanticCustomError("aadhaar_number", "Leave out Aadhaar numbers: we never keep one.")
    return value


def _text(min_length: int, max_length: int) -> object:
    """Printable text, trimmed, with no control characters."""
    return StringConstraints(
        strip_whitespace=True,
        min_length=min_length,
        max_length=max_length,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    )


def _indian_mobile(value: str) -> str:
    phone = normalize_indian_mobile(value)
    if phone is None:
        raise PydanticCustomError("phone_invalid", "Enter a 10-digit Indian mobile number.")
    return phone


def _signature_name(value: str) -> str:
    name = typed_name(value)
    if name is None:
        raise PydanticCustomError(
            "name_invalid", "Type your full name in letters, as you'd sign it."
        )
    return name


def _upper(value: str) -> str:
    return value.upper()


# Free text the police form takes; never an Aadhaar number, whichever field it's typed into.
DetailText = Annotated[str, _text(2, 80), AfterValidator(_no_aadhaar_number)]
LongDetailText = Annotated[str, _text(2, 200), AfterValidator(_no_aadhaar_number)]
IndianMobile = Annotated[str, StringConstraints(max_length=32), AfterValidator(_indian_mobile)]


# The rent agreement.


class AgreementSignatureView(ApiModel):
    """A side's signature as the parties see it: whose, the name they typed, and when."""

    signer: Signer
    name: str
    signed_at: datetime


class RentAgreement(ApiModel):
    """A booking's rent agreement, as the student or the owner sees it. ``text`` is Markdown in
    the subset the owner agreement uses; ``textSha256`` is what a signature names."""

    booking: str
    status: AgreementStatus
    # Which side the caller is.
    you: Signer
    template_version: str
    # Not reviewed by a lawyer yet: the text says so too.
    draft: bool
    text: str
    text_sha256: str
    # Whether the text has all it needs before anyone signs, and what it lacks if not.
    ready: bool
    missing: list[str]
    # Whether the caller may sign now: their side hasn't, and the agreement is ready and open.
    can_sign: bool
    signatures: list[AgreementSignatureView]
    signed_at: datetime | None
    voided_at: datetime | None


class SignatureEvidence(ApiModel):
    """A signature with its evidence, for ops: the account, the name typed, the server's time, the
    IP address and browser it came from, and the text it names."""

    signer: Signer
    user: uuid.UUID
    name: str
    signed_at: datetime
    ip_address: str
    user_agent: str | None
    text_sha256: str
    template_version: str


class OpsRentAgreement(ApiModel):
    """A booking's rent agreement with every signature's evidence, read-only."""

    booking: str
    status: AgreementStatus
    template_version: str
    draft: bool
    text: str
    text_sha256: str
    ready: bool
    missing: list[str]
    signatures: list[SignatureEvidence]
    # When the agreement was first saved; null while nobody has acted on it yet.
    created_at: datetime | None
    signed_at: datetime | None
    voided_at: datetime | None
    booking_ended_at: datetime | None


class SigningCodeSent(ApiModel):
    """A code is on its way to the signer. Sign with it before ``expiresAt``."""

    expires_at: datetime
    # When another code may be asked for.
    resend_after: datetime
    # The code itself, only in local development, where nothing is really sent. Null wherever
    # codes are sent.
    development_code: str | None = None


class SignatureRequest(ApiModel):
    """Signing: the code that was sent, the signer's full name as they sign it, and the hash of
    the text they read (``textSha256``). A text that has changed since is refused."""

    code: Annotated[str, Field(pattern=rf"^[0-9]{{{CODE_DIGITS}}}$")]
    full_name: Annotated[
        str,
        StringConstraints(min_length=TYPED_NAME_MIN, max_length=TYPED_NAME_MAX * 2),
        AfterValidator(_signature_name),
    ]
    text_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


# Police verification.


class AddressDetails(ApiModel):
    line: LongDetailText
    city: DetailText
    district: DetailText
    state: DetailText
    pin_code: Annotated[str, Field(pattern=r"^[1-9][0-9]{5}$")]
    # The police station the address comes under, if known.
    police_station: DetailText | None = None


class ReferenceDetails(ApiModel):
    """Someone who knows the tenant."""

    name: DetailText
    phone: IndianMobile
    relation: Annotated[str, _text(2, 40), AfterValidator(_no_aadhaar_number)]


class TenantDetails(ApiModel):
    """What the police form asks about the tenant. An identity document is its type and the last
    four characters of its number only: never a full Aadhaar number, or any other."""

    full_name: DetailText
    # Father's, mother's or guardian's name.
    parent_name: DetailText
    date_of_birth: Annotated[date, Field(ge=date(1900, 1, 1))]
    gender: Gender
    phone: IndianMobile
    permanent_address: AddressDetails
    occupation: Occupation
    # Their college or workplace, with its city.
    institution: Annotated[str, _text(2, 120), AfterValidator(_no_aadhaar_number)]
    id_type: IdType
    id_last4: Annotated[str, Field(pattern=r"^[A-Za-z0-9]{4}$"), AfterValidator(_upper)]
    references: Annotated[
        list[ReferenceDetails], Field(default_factory=list, max_length=MAX_REFERENCES)
    ]


class TenantDetailsInput(TenantDetails):
    """The student's details, with their agreement to share them with the PG's owner for the
    police (it can't be anything but true: nothing is pre-ticked)."""

    consent: Literal[True]


class StudentPoliceVerification(ApiModel):
    booking: str
    status: PoliceVerificationStatus
    # What the student gave, as they gave it; null before they have, and once erased.
    details: TenantDetails | None
    details_submitted_at: datetime | None
    submitted_to_police_at: datetime | None
    police_reference: str | None
    verified_at: datetime | None
    # Whether they may give or correct their details now.
    can_edit: bool
    erased: bool


class TenancySummary(ApiModel):
    """The tenancy the police form describes, as the agreement has it."""

    booking: str
    licensor: str
    pg_name: str
    pg_address: str
    room: str
    move_in: date
    planned_move_out: date


class AcknowledgementFile(ApiModel):
    content_type: str
    # Signed for five minutes.
    url: str


class OwnerPoliceVerification(ApiModel):
    """The tenant's police verification, as the owner submits it: the details to copy onto the
    Delhi Police portal, the tenancy, and the acknowledgement once uploaded."""

    booking: str
    status: PoliceVerificationStatus
    details: TenantDetails | None
    tenancy: TenancySummary
    details_submitted_at: datetime | None
    submitted_to_police_at: datetime | None
    police_reference: str | None
    acknowledgement: list[AcknowledgementFile]
    verified_at: datetime | None
    can_mark_submitted: bool
    can_mark_verified: bool
    erased: bool


class OpsPoliceVerification(ApiModel):
    """The same, for ops: read-only."""

    booking: str
    status: PoliceVerificationStatus
    details: TenantDetails | None
    tenancy: TenancySummary
    details_submitted_at: datetime | None
    submitted_to_police_at: datetime | None
    police_reference: str | None
    acknowledgement: list[AcknowledgementFile]
    verified_at: datetime | None
    erased: bool


class PoliceSubmission(ApiModel):
    """The owner submitted the details on the Delhi Police portal: the acknowledgement they
    uploaded as a private document, and its number if the portal gave one."""

    acknowledgement: uuid.UUID
    reference: Annotated[str, _text(1, 60)] | None = None
