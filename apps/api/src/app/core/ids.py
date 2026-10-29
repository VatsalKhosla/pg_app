"""Identifiers people and clients see: UUIDv7 public ids, booking codes and grievance ticket
numbers (ARCHITECTURE §5).

Tables keep ``bigint`` identity keys internally; the API only ever shows a ``public_id`` (UUIDv7,
time-ordered, so its index stays compact) or a code: a booking's such as ``BK-7F3K2Q9M``, or a
grievance's ticket number such as ``GR-4M8Q2T7K``. Codes use Crockford's base32 alphabet (no I,
L, O or U), so one read out over the phone is hard to get wrong. Eight random characters give
2^40 codes and say nothing about how many there are; a unique constraint plus a retry deals with
the rare collision.
"""

import re
import secrets
import uuid
from typing import Final

CROCKFORD_ALPHABET: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
BOOKING_CODE_PREFIX: Final = "BK-"
BOOKING_CODE_LENGTH: Final = 8
BOOKING_CODE_PATTERN: Final = re.compile(r"BK-[0-9A-HJKMNP-TV-Z]{8}")
TICKET_NUMBER_PREFIX: Final = "GR-"
TICKET_NUMBER_PATTERN: Final = re.compile(r"GR-[0-9A-HJKMNP-TV-Z]{8}")

# Crockford decoding: lower case is accepted, O reads as 0, and I or L read as 1.
_DECODE: Final = {char: char for char in CROCKFORD_ALPHABET} | {"O": "0", "I": "1", "L": "1"}


def new_public_id() -> uuid.UUID:
    return uuid.uuid7()


def _new_code(prefix: str) -> str:
    return prefix + "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(BOOKING_CODE_LENGTH))


def _normalize_code(raw: str, prefix: str) -> str | None:
    """The canonical form of a code someone typed, or None if it can't be one with ``prefix``.

    Accepts any case, spaces and hyphens, and the usual mix-ups (O for 0, I or L for 1).
    """
    compact = re.sub(r"[\s-]", "", raw).upper()
    letters = prefix.rstrip("-")
    # Strip the prefix only by length, so a code whose body starts with its letters still works.
    if len(compact) == len(letters) + BOOKING_CODE_LENGTH and compact.startswith(letters):
        compact = compact[len(letters) :]
    if len(compact) != BOOKING_CODE_LENGTH:
        return None
    try:
        body = "".join(_DECODE[char] for char in compact)
    except KeyError:
        return None
    return prefix + body


def new_booking_code() -> str:
    return _new_code(BOOKING_CODE_PREFIX)


def normalize_booking_code(raw: str) -> str | None:
    """The canonical form of a booking code someone typed, or None if it can't be one."""
    return _normalize_code(raw, BOOKING_CODE_PREFIX)


def new_ticket_number() -> str:
    return _new_code(TICKET_NUMBER_PREFIX)


def normalize_ticket_number(raw: str) -> str | None:
    """The canonical form of a grievance ticket number someone typed, or None if it can't be
    one."""
    return _normalize_code(raw, TICKET_NUMBER_PREFIX)
