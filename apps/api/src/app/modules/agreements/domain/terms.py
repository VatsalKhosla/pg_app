"""What a rent agreement says (ADR 0070): the booking's facts written into a template. Pure.

The template is Markdown in the subset the web app renders (headings, paragraphs, "- " lists and
**bold**), with ``{blanks}`` for the booking's facts. The text it makes is what both sides read
and sign, so it is the same for the same facts, byte for byte, and its SHA-256 names it.

Every amount is the booking's own, as it copied it from the quote (rule 5): nothing here works
money out.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from app.core.money import format_rupees

# A template's blanks: {like_this}.
_BLANK: Final = re.compile(r"\{([a-z_]+)\}")
_MONTHS: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
# What the text says while the student's account has no name: signing waits for one.
NAME_MISSING: Final = "[the student's full name, once they add it to their account]"


class ChargeCadence(StrEnum):
    MONTHLY = "monthly"
    # Billed on use (electricity by the unit), with a monthly estimate.
    METERED = "metered"
    ONE_TIME = "one_time"


@dataclass(frozen=True, slots=True)
class ChargeTerm:
    """A mandatory charge as the student's quote showed it."""

    label: str
    cadence: ChargeCadence
    # A monthly or one-time charge's amount; a metered one's monthly estimate.
    amount_paise: int
    # A metered charge's rate and its unit ("kWh").
    rate_paise: int | None = None
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class Tenancy:
    """A booking's facts, as its agreement states them."""

    booking_code: str
    # The owner's legal name, and the name their business trades under.
    licensor: str
    licensor_business: str
    # The student's name from their account; None until they've given one.
    licensee: str | None
    pg_name: str
    pg_address: str
    room_type: str
    room: str
    bed: str
    move_in: date
    stay_months: int
    planned_move_out: date
    monthly_rent_paise: int
    deposit_paise: int
    token_paise: int
    due_at_move_in_paise: int
    monthly_charges_paise: int
    one_time_charges_paise: int
    charges: tuple[ChargeTerm, ...] = ()


class TemplateError(ValueError):
    """A template with a blank nothing fills."""


def text_sha256(text: str) -> str:
    """What a signature names: the SHA-256 of exactly this text, in UTF-8, as hex."""
    return hashlib.sha256(text.encode()).hexdigest()


def blanks(template: str) -> frozenset[str]:
    return frozenset(_BLANK.findall(template))


def spoken_day(day: date) -> str:
    """A date as the agreement writes it: 20 August 2027."""
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def _plain(value: str) -> str:
    """A fact as plain text on one line: whatever someone typed into a name or an address can't
    start a heading or a list item, or turn into bold or a link, in the agreement."""
    flat = " ".join(value.split())
    return flat.replace("**", "").replace("[", "(").replace("]", ")")


def _charge_line(charge: ChargeTerm) -> str:
    label = _plain(charge.label)
    match charge.cadence:
        case ChargeCadence.MONTHLY:
            return f"- {label}: {format_rupees(charge.amount_paise)} a month"
        case ChargeCadence.METERED:
            rate = "" if charge.rate_paise is None else f"{format_rupees(charge.rate_paise)} per "
            unit = _plain(charge.unit or "unit")
            estimate = format_rupees(charge.amount_paise)
            return f"- {label}: {rate}{unit} used, about {estimate} a month"
        case ChargeCadence.ONE_TIME:
            return f"- {label}: {format_rupees(charge.amount_paise)} once"


def _months(count: int) -> str:
    return "1 month" if count == 1 else f"{count} months"


def facts(tenancy: Tenancy, *, brand: str) -> dict[str, str]:
    """Every blank a template may use, filled from ``tenancy``."""
    charges = [_charge_line(charge) for charge in tenancy.charges] or ["- None."]
    return {
        "brand": _plain(brand),
        "booking_code": _plain(tenancy.booking_code),
        "licensor": _plain(tenancy.licensor),
        "licensor_business": _plain(tenancy.licensor_business),
        "licensee": NAME_MISSING if tenancy.licensee is None else _plain(tenancy.licensee),
        "pg_name": _plain(tenancy.pg_name),
        "pg_address": _plain(tenancy.pg_address),
        "room_type": _plain(tenancy.room_type),
        "room": _plain(tenancy.room),
        "bed": _plain(tenancy.bed),
        "move_in": spoken_day(tenancy.move_in),
        "stay_months": _months(tenancy.stay_months),
        "planned_move_out": spoken_day(tenancy.planned_move_out),
        "monthly_rent": format_rupees(tenancy.monthly_rent_paise),
        "deposit": format_rupees(tenancy.deposit_paise),
        "token": format_rupees(tenancy.token_paise),
        "due_at_move_in": format_rupees(tenancy.due_at_move_in_paise),
        "monthly_charges": format_rupees(tenancy.monthly_charges_paise),
        "one_time_charges": format_rupees(tenancy.one_time_charges_paise),
        "charges": "\n".join(charges),
    }


FILLED: Final = frozenset(
    facts(
        Tenancy(
            booking_code="",
            licensor="",
            licensor_business="",
            licensee=None,
            pg_name="",
            pg_address="",
            room_type="",
            room="",
            bed="",
            move_in=date(2000, 1, 1),
            stay_months=1,
            planned_move_out=date(2000, 2, 1),
            monthly_rent_paise=0,
            deposit_paise=0,
            token_paise=0,
            due_at_move_in_paise=0,
            monthly_charges_paise=0,
            one_time_charges_paise=0,
        ),
        brand="",
    )
)


def render(template: str, tenancy: Tenancy, *, brand: str) -> str:
    """The agreement's text: ``template`` with every blank filled. A blank the facts don't fill is
    a TemplateError, never left in the text."""
    unknown = blanks(template) - FILLED
    if unknown:
        msg = f"the template has blanks nothing fills: {', '.join(sorted(unknown))}"
        raise TemplateError(msg)
    values = facts(tenancy, brand=brand)
    return _BLANK.sub(lambda match: values[match.group(1)], template)


def missing(tenancy: Tenancy) -> list[str]:
    """What the text still lacks before anyone may sign it: empty when it's complete."""
    return [] if tenancy.licensee else ["the student's name"]
