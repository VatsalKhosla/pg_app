"""Identifiers people and clients see: UUIDv7 public ids and booking codes (ARCHITECTURE §5).

Tables keep ``bigint`` identity keys internally; the API only ever shows a ``public_id`` (UUIDv7,
time-ordered, so its index stays compact) or a booking code such as ``BK-7F3K2Q9M``. Codes use
Crockford's base32 alphabet (no I, L, O or U), so one read out over the phone is hard to get
wrong. Eight characters give 2^40 codes; the unique constraint on ``bookings.code`` plus a retry
deals with the rare collision.
"""

import re
import secrets
import uuid
from typing import Final

CROCKFORD_ALPHABET: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
BOOKING_CODE_PREFIX: Final = "BK-"
BOOKING_CODE_LENGTH: Final = 8
BOOKING_CODE_PATTERN: Final = re.compile(r"BK-[0-9A-HJKMNP-TV-Z]{8}")

# Crockford decoding: lower case is accepted, O reads as 0, and I or L read as 1.
_DECODE: Final = {char: char for char in CROCKFORD_ALPHABET} | {"O": "0", "I": "1", "L": "1"}


def new_public_id() -> uuid.UUID:
    return uuid.uuid7()


def new_booking_code() -> str:
    body = "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(BOOKING_CODE_LENGTH))
    return BOOKING_CODE_PREFIX + body


def normalize_booking_code(raw: str) -> str | None:
    """The canonical form of a code someone typed, or None if it can't be a booking code.

    Accepts any case, spaces and hyphens, and the usual mix-ups (O for 0, I or L for 1).
    """
    compact = re.sub(r"[\s-]", "", raw).upper()
    prefix = BOOKING_CODE_PREFIX.rstrip("-")
    # Strip the prefix only by length, so a code whose body starts with "BK" still works.
    if len(compact) == len(prefix) + BOOKING_CODE_LENGTH and compact.startswith(prefix):
        compact = compact[len(prefix) :]
    if len(compact) != BOOKING_CODE_LENGTH:
        return None
    try:
        body = "".join(_DECODE[char] for char in compact)
    except KeyError:
        return None
    return BOOKING_CODE_PREFIX + body
