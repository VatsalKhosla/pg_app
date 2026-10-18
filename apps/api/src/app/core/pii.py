"""Masking personal data before it leaves the process (logs and error reports).

Phone numbers are masked to their last four digits (CLAUDE.md, ARCHITECTURE §17).
"""

import re
from collections.abc import Mapping

# International numbers (+91 98765 43210, +919876543210) and Indian mobile numbers without the
# plus sign (919876543210, 98765 43210, 09876543210). Digits glued to letters or to more digits
# (ids, hashes, longer numbers) are left alone.
_PHONE = re.compile(r"(?<![\w+])(?:\+\d[\d -]{8,16}\d|(?:91[ -]?|0)?[6-9]\d{4}[ -]?\d{5})(?!\w)")


def _last_four(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    return "******" + digits[-4:]


def mask_text(text: str) -> str:
    return _PHONE.sub(_last_four, text)


def mask_pii(value: object) -> object:
    """Return ``value`` with every phone number masked, looking inside mappings and sequences."""
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, Mapping):
        return {key: mask_pii(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_pii(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_pii(item) for item in value)
    return value
