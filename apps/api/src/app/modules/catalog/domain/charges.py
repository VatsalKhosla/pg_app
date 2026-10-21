"""Mandatory charges (ARCHITECTURE §6): what a student pays on top of the rent, shown in full
before booking (CLAUDE.md rule 7). Amounts are integer paise.

A charge is one of three shapes:
- **monthly:** a fixed amount every month, such as maintenance or Wi-Fi;
- **metered:** a rate per unit, such as electricity per kWh, with the owner's monthly estimate,
  so the full monthly cost can still be shown;
- **one-time:** an amount at move-in, such as a registration fee.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.money import Paise

if TYPE_CHECKING:
    from collections.abc import Sequence

MAX_CHARGES: Final = 12
LABEL_MAX_LENGTH: Final = 60
UNIT_MAX_LENGTH: Final = 16


class ChargeKind(StrEnum):
    ELECTRICITY = "electricity"
    WATER = "water"
    MAINTENANCE = "maintenance"
    INTERNET = "internet"
    LAUNDRY = "laundry"
    FOOD = "food"
    REGISTRATION = "registration"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class MonthlyCharge:
    kind: ChargeKind
    label: str
    amount: Paise


@dataclass(frozen=True, slots=True)
class MeteredCharge:
    kind: ChargeKind
    label: str
    # Per unit, such as per kWh.
    rate: Paise
    unit: str
    monthly_estimate: Paise


@dataclass(frozen=True, slots=True)
class OneTimeCharge:
    kind: ChargeKind
    label: str
    amount: Paise


type MandatoryCharge = MonthlyCharge | MeteredCharge | OneTimeCharge


def charge_problems(charges: Sequence[MandatoryCharge]) -> list[str]:
    """What is wrong with a category's charges; empty when nothing is."""
    problems = []
    if len(charges) > MAX_CHARGES:
        problems.append(f"at most {MAX_CHARGES} charges")
    seen: set[tuple[ChargeKind, str]] = set()
    for charge in charges:
        label = charge.label.strip()
        if not label or len(label) > LABEL_MAX_LENGTH:
            problems.append(f"each charge needs a label of 1 to {LABEL_MAX_LENGTH} characters")
        key = (charge.kind, label.casefold())
        if key in seen:
            problems.append(f"{label}: listed twice")
        seen.add(key)
        match charge:
            case MonthlyCharge(amount=amount) | OneTimeCharge(amount=amount):
                if amount <= 0:
                    problems.append(f"{label}: the amount must be more than zero")
            case MeteredCharge(rate=rate, unit=unit, monthly_estimate=estimate):
                if rate <= 0:
                    problems.append(f"{label}: the rate must be more than zero")
                if not unit.strip() or len(unit) > UNIT_MAX_LENGTH:
                    problems.append(f"{label}: the unit needs 1 to {UNIT_MAX_LENGTH} characters")
                if estimate <= 0:
                    problems.append(f"{label}: the monthly estimate must be more than zero")
    return problems


def monthly_total(charges: Sequence[MandatoryCharge]) -> Paise:
    """What the charges come to each month: fixed amounts plus metered estimates."""
    total = 0
    for charge in charges:
        match charge:
            case MonthlyCharge(amount=amount):
                total += amount
            case MeteredCharge(monthly_estimate=estimate):
                total += estimate
            case OneTimeCharge():
                pass
    return Paise(total)


def one_time_total(charges: Sequence[MandatoryCharge]) -> Paise:
    """What the charges come to once, at move-in."""
    return Paise(sum(charge.amount for charge in charges if isinstance(charge, OneTimeCharge)))
