"""Money as integer paise and rates as basis points, with exact half-up rounding (CLAUDE.md #12).

No floats anywhere: amounts are ``int`` paise (₹1 = 100 paise) and rates are ``int`` basis points
(1% = 100 bps, 100% = 10,000 bps). Rounding is half-up, ties away from zero, and happens only
where a spec says so (ARCHITECTURE §8.3). Pure: no I/O and no clock.
"""

from typing import Final, NewType

Paise = NewType("Paise", int)
BasisPoints = NewType("BasisPoints", int)

PAISE_PER_RUPEE: Final = 100
BPS_PER_WHOLE: Final = 10_000


def rupees(amount: int) -> Paise:
    """Whole rupees as paise: ``rupees(10_000) == 1_000_000``."""
    return Paise(amount * PAISE_PER_RUPEE)


def divide_round_half_up(numerator: int, denominator: int) -> int:
    """``numerator / denominator`` rounded to the nearest integer, ties away from zero."""
    if denominator <= 0:
        msg = f"denominator must be positive, got {denominator}"
        raise ValueError(msg)
    if numerator < 0:
        return -divide_round_half_up(-numerator, denominator)
    return (2 * numerator + denominator) // (2 * denominator)


def apply_bps(amount: int, bps: int) -> int:
    """``amount * bps / 10,000``, rounded half-up: e.g. 30% (3,000 bps) of ₹10,000 is ₹3,000."""
    return divide_round_half_up(amount * bps, BPS_PER_WHOLE)


def round_to_step(amount: int, step: int) -> int:
    """``amount`` rounded half-up to the nearest multiple of ``step`` (₹50 is a step of 5,000)."""
    if step <= 0:
        msg = f"step must be positive, got {step}"
        raise ValueError(msg)
    return divide_round_half_up(amount, step) * step


def format_inr(paise: int) -> str:
    """Rupees with Indian digit grouping, for logs and messages: ``123_456_789 → ₹12,34,567.89``.

    The web app formats amounts for people with ``Intl.NumberFormat('en-IN')``; this is for the
    server's own text.
    """
    rupee_part, paise_part = divmod(abs(paise), PAISE_PER_RUPEE)
    digits = str(rupee_part)
    if len(digits) > 3:
        head, groups = digits[:-3], [digits[-3:]]
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join(groups)
    sign = "-" if paise < 0 else ""
    return f"{sign}₹{digits}.{paise_part:02d}"


def format_rupees(paise: int) -> str:
    """Rupees as people read them: ``₹10,300`` when whole, ``₹10,300.50`` otherwise."""
    text = format_inr(paise)
    return text.removesuffix(".00")
