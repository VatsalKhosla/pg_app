"""Police verification of a tenant (ADR 0070). Pure.

Landlords in Delhi register their tenants with Delhi Police. Here the student gives the details
the police form asks for, the site lays them out as a pre-filled summary, and the owner submits
them on the Delhi Police portal, uploads the acknowledgement and later says the police have
verified the tenant:

    not_started ─ student gives details ─▶ details_submitted ─ owner uploads the acknowledgement
        ─▶ submitted_to_police ─ owner says it's verified ─▶ verified

The student may correct their details until the owner has submitted them; nothing goes back. Once
the booking has ended, nothing moves.

**No Aadhaar numbers, ever.** An identity document is recorded only as its type and the last four
characters of its number: the owner copies the full number from the original document onto the
portal. Any text that holds what looks like an Aadhaar number (twelve digits, spaced or not) is
refused, whichever field it was typed into.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

# The same choices a profile offers (ARCHITECTURE §6), as the police form asks them.
from app.modules.identity.domain.profile import Gender


class PoliceVerificationStatus(StrEnum):
    NOT_STARTED = "not_started"
    DETAILS_SUBMITTED = "details_submitted"
    SUBMITTED_TO_POLICE = "submitted_to_police"
    VERIFIED = "verified"


class VerificationEvent(StrEnum):
    # The student gives their details, or corrects them.
    GIVE_DETAILS = "give_details"
    # The owner submitted them on the police portal and uploaded the acknowledgement.
    SUBMIT_TO_POLICE = "submit_to_police"
    # The police verified the tenant, as the owner tells us.
    MARK_VERIFIED = "mark_verified"


_TABLE: Final[
    dict[tuple[PoliceVerificationStatus, VerificationEvent], PoliceVerificationStatus]
] = {
    (PoliceVerificationStatus.NOT_STARTED, VerificationEvent.GIVE_DETAILS): (
        PoliceVerificationStatus.DETAILS_SUBMITTED
    ),
    (PoliceVerificationStatus.DETAILS_SUBMITTED, VerificationEvent.GIVE_DETAILS): (
        PoliceVerificationStatus.DETAILS_SUBMITTED
    ),
    (PoliceVerificationStatus.DETAILS_SUBMITTED, VerificationEvent.SUBMIT_TO_POLICE): (
        PoliceVerificationStatus.SUBMITTED_TO_POLICE
    ),
    (PoliceVerificationStatus.SUBMITTED_TO_POLICE, VerificationEvent.MARK_VERIFIED): (
        PoliceVerificationStatus.VERIFIED
    ),
}
_REASONS: Final = {
    VerificationEvent.GIVE_DETAILS: "The owner has submitted these details to the police already.",
    VerificationEvent.SUBMIT_TO_POLICE: "This needs the student's details, not yet submitted.",
    VerificationEvent.MARK_VERIFIED: "This needs submitting to the police first.",
}


class VerificationRefusedError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def advance(
    status: PoliceVerificationStatus, event: VerificationEvent, *, booking_ended: bool
) -> PoliceVerificationStatus:
    """The status after ``event``, or VerificationRefusedError with the reason."""
    if booking_ended:
        raise VerificationRefusedError("The booking has ended: its police verification is closed.")
    found = _TABLE.get((status, event))
    if found is None:
        if status is PoliceVerificationStatus.VERIFIED:
            raise VerificationRefusedError("The police have verified this tenant already.")
        if event is VerificationEvent.SUBMIT_TO_POLICE and (
            status is PoliceVerificationStatus.SUBMITTED_TO_POLICE
        ):
            raise VerificationRefusedError("These details are with the police already.")
        raise VerificationRefusedError(_REASONS[event])
    return found


def allowed(
    status: PoliceVerificationStatus, event: VerificationEvent, *, booking_ended: bool
) -> bool:
    return not booking_ended and (status, event) in _TABLE


class Occupation(StrEnum):
    STUDENT = "student"
    WORKING = "working"
    OTHER = "other"


class IdType(StrEnum):
    """Identity documents the police form accepts, as their type and last four characters only.
    [The founders and a lawyer confirm the list against the current Delhi Police form.]"""

    AADHAAR = "aadhaar"
    PASSPORT = "passport"
    VOTER_ID = "voter_id"
    DRIVING_LICENCE = "driving_licence"
    PAN = "pan"


# Twelve digits in a row, or in groups of four split by spaces, dots or hyphens: an Aadhaar
# number's shape. Longer runs of digits are refused too, as they hold one.
_AADHAAR_LIKE: Final = re.compile(r"\d{4}[ .-]?\d{4}[ .-]?\d{4}")
_LAST_FOUR: Final = re.compile(r"[A-Z0-9]{4}")
_DIGITS: Final = re.compile(r"[0-9]{4}")
OLDEST_YEARS: Final = 100
YOUNGEST_YEARS: Final = 15
MAX_REFERENCES: Final = 2


def holds_aadhaar_like_number(text: str) -> bool:
    """Whether ``text`` holds what may be an Aadhaar number: twelve digits, spaced or not."""
    return _AADHAAR_LIKE.search(text) is not None


@dataclass(frozen=True, slots=True)
class Address:
    line: str
    city: str
    district: str
    state: str
    pin_code: str
    # The police station the address comes under, if the student knows it.
    police_station: str | None = None


@dataclass(frozen=True, slots=True)
class Reference:
    """Someone who knows the tenant, as the police form asks for."""

    name: str
    phone_e164: str
    relation: str


@dataclass(frozen=True, slots=True)
class TenantDetails:
    """What the student gives for the police form. Kept sealed; see app/core/sealing.py."""

    full_name: str
    # Father's, mother's or guardian's name.
    parent_name: str
    date_of_birth: date
    gender: Gender
    phone_e164: str
    permanent_address: Address
    occupation: Occupation
    # Their college or workplace, with its city.
    institution: str
    id_type: IdType
    # Only the last four characters of the document's number.
    id_last4: str
    references: tuple[Reference, ...] = ()

    def texts(self) -> list[str]:
        """Every free text in the details, for the Aadhaar check."""
        address = self.permanent_address
        found = [
            self.full_name,
            self.parent_name,
            self.institution,
            address.line,
            address.city,
            address.district,
            address.state,
            address.pin_code,
            address.police_station or "",
        ]
        for reference in self.references:
            found += [reference.name, reference.relation]
        return found


def _years_between(earlier: date, later: date) -> int:
    return later.year - earlier.year - ((later.month, later.day) < (earlier.month, earlier.day))


def problems(details: TenantDetails, *, today: date) -> list[str]:
    """What the police form couldn't take as given; empty when nothing."""
    found: list[str] = []
    if any(holds_aadhaar_like_number(text) for text in details.texts()):
        found.append("Leave out Aadhaar numbers: we never keep one.")
    if details.id_type is IdType.AADHAAR:
        if not _DIGITS.fullmatch(details.id_last4):
            found.append("An Aadhaar number's last four characters are digits.")
    elif not _LAST_FOUR.fullmatch(details.id_last4):
        found.append("Give the last four letters or digits of the document's number.")
    age = _years_between(details.date_of_birth, today)
    if details.date_of_birth > today or not YOUNGEST_YEARS <= age <= OLDEST_YEARS:
        found.append(
            f"The date of birth must make you {YOUNGEST_YEARS} to {OLDEST_YEARS} years old."
        )
    if len(details.references) > MAX_REFERENCES:
        found.append(f"Give at most {MAX_REFERENCES} people who know you.")
    if any(reference.phone_e164 == details.phone_e164 for reference in details.references):
        found.append("Someone who knows you needs a phone number other than yours.")
    return found


def to_json(details: TenantDetails) -> dict[str, object]:
    """The details as they're sealed: plain JSON, read back by ``from_json``."""
    address = details.permanent_address
    return {
        "full_name": details.full_name,
        "parent_name": details.parent_name,
        "date_of_birth": details.date_of_birth.isoformat(),
        "gender": details.gender.value,
        "phone_e164": details.phone_e164,
        "permanent_address": {
            "line": address.line,
            "city": address.city,
            "district": address.district,
            "state": address.state,
            "pin_code": address.pin_code,
            "police_station": address.police_station,
        },
        "occupation": details.occupation.value,
        "institution": details.institution,
        "id_type": details.id_type.value,
        "id_last4": details.id_last4,
        "references": [
            {"name": item.name, "phone_e164": item.phone_e164, "relation": item.relation}
            for item in details.references
        ],
    }


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = "sealed details aren't what to_json wrote"
        raise TypeError(msg)
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        msg = "sealed details aren't what to_json wrote"
        raise TypeError(msg)
    return value


def from_json(stored: Mapping[str, object]) -> TenantDetails:
    address = _mapping(stored["permanent_address"])
    station = address.get("police_station")
    references = stored.get("references", [])
    if not isinstance(references, list):
        msg = "sealed details aren't what to_json wrote"
        raise TypeError(msg)
    return TenantDetails(
        full_name=_text(stored["full_name"]),
        parent_name=_text(stored["parent_name"]),
        date_of_birth=date.fromisoformat(_text(stored["date_of_birth"])),
        gender=Gender(_text(stored["gender"])),
        phone_e164=_text(stored["phone_e164"]),
        permanent_address=Address(
            line=_text(address["line"]),
            city=_text(address["city"]),
            district=_text(address["district"]),
            state=_text(address["state"]),
            pin_code=_text(address["pin_code"]),
            police_station=None if station is None else _text(station),
        ),
        occupation=Occupation(_text(stored["occupation"])),
        institution=_text(stored["institution"]),
        id_type=IdType(_text(stored["id_type"])),
        id_last4=_text(stored["id_last4"]),
        references=tuple(
            Reference(
                name=_text(_mapping(item)["name"]),
                phone_e164=_text(_mapping(item)["phone_e164"]),
                relation=_text(_mapping(item)["relation"]),
            )
            for item in references
        ),
    )
