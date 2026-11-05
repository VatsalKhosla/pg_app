"""An owner's invoice (ARCHITECTURE §9.5; step 6.5, ADR 0061). Pure.

An invoice is issued as a booking settles: the placement fee and its GST, less the student's token,
which counts toward the fee (PRODUCT_CONTEXT §6). What's left is the balance the owner pays through
a payment link. A token larger than the fee leaves something owed to the owner instead, which only
split settlement may pay them (rule 10).

Numbers run in one series per Indian financial year, April to March, with no gaps. GST allows 16
characters (CGST Rules, rule 46(b)), which ``FY2027-28/000123`` is.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from datetime import date

APRIL: Final = 4
MAX_NUMBER_LENGTH: Final = 16
SERIAL_DIGITS: Final = 6
BPS_PER_PERCENT: Final = 100


class InvoiceStatus(StrEnum):
    ISSUED = "issued"
    PAID = "paid"


def financial_year(on: date) -> str:
    """The financial year ``on`` falls in, as ``2027-28``."""
    first = on.year if on.month >= APRIL else on.year - 1
    return f"{first}-{(first + 1) % 100:02d}"


def invoice_number(year: str, serial: int) -> str:
    """``FY2027-28/000123``. Raises ValueError for a serial that won't fit GST's 16 characters."""
    number = f"FY{year}/{serial:0{SERIAL_DIGITS}d}"
    if serial < 1 or len(number) > MAX_NUMBER_LENGTH:
        msg = f"serial {serial} makes no invoice number GST allows"
        raise ValueError(msg)
    return number


@dataclass(frozen=True, slots=True)
class InvoiceAmounts:
    # The fee before GST: the taxable value.
    fee_paise: int
    gst_paise: int
    total_paise: int
    # What the token paid of the total, and what it came to beyond it, owed to the owner.
    token_applied_paise: int
    token_over_paise: int
    balance_due_paise: int


def invoice_amounts(*, total_paise: int, gst_paise: int, token_paise: int) -> InvoiceAmounts:
    """What an invoice says, from what the booking kept of its quote: the owner's total with its
    GST, whichever way the GST was worked out (``gst_mode``), and the token."""
    if min(total_paise, gst_paise, token_paise) < 0 or gst_paise > total_paise:
        msg = "an invoice needs a total of at least its GST, and nothing negative"
        raise ValueError(msg)
    applied = min(token_paise, total_paise)
    return InvoiceAmounts(
        fee_paise=total_paise - gst_paise,
        gst_paise=gst_paise,
        total_paise=total_paise,
        token_applied_paise=applied,
        token_over_paise=token_paise - applied,
        balance_due_paise=total_paise - applied,
    )


def status_on_issue(amounts: InvoiceAmounts) -> InvoiceStatus:
    """An invoice the token paid in full is paid as it's issued."""
    return InvoiceStatus.PAID if amounts.balance_due_paise == 0 else InvoiceStatus.ISSUED


def percent(bps: int) -> str:
    """Basis points as people write a rate: ``18%``, ``12.5%``."""
    whole, part = divmod(bps, BPS_PER_PERCENT)
    return f"{whole}%" if part == 0 else f"{whole}.{part:02d}".rstrip("0") + "%"
