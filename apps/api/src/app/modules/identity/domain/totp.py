"""Authenticator-app codes (TOTP, RFC 6238) for the staff sign-in fallback (ARCHITECTURE §12).

A code is six digits: HMAC-SHA-1 over the number of 30-second steps since the Unix epoch, the
defaults every authenticator app understands. A code counts for its own step and one step either
side, to allow for a phone's clock drifting, and each step's code works only once.
"""

import base64
import hashlib
import hmac
import struct
from typing import TYPE_CHECKING, Final
from urllib.parse import quote, urlencode

if TYPE_CHECKING:
    from datetime import datetime

DIGITS: Final = 6
PERIOD_SECONDS: Final = 30
# Steps either side of the current one whose codes still count.
DRIFT_STEPS: Final = 1
# 160 bits, the length RFC 4226 recommends for an HMAC-SHA-1 key.
SECRET_BYTES: Final = 20
# Each enrolment's secret is derived from SECRET_KEY and a random salt of this length.
SALT_BYTES: Final = 16


def time_step(now: datetime) -> int:
    return int(now.timestamp()) // PERIOD_SECONDS


def code_at(secret: bytes, step: int, *, digits: int = DIGITS) -> str:
    """The code for ``step``: HOTP (RFC 4226) with the step as the counter."""
    digest = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    (number,) = struct.unpack(">I", digest[offset : offset + 4])
    return f"{(number & 0x7FFF_FFFF) % 10**digits:0{digits}d}"


def matching_step(
    secret: bytes, code: str, *, now: datetime, last_used_step: int | None
) -> int | None:
    """The step ``code`` belongs to, if it is current (give or take the drift) and newer than the
    last code used; otherwise None. Every candidate is compared, in constant time."""
    if len(code) != DIGITS or not (code.isascii() and code.isdigit()):
        return None
    current = time_step(now)
    found: int | None = None
    for step in range(current - DRIFT_STEPS, current + DRIFT_STEPS + 1):
        fresh = last_used_step is None or step > last_used_step
        if hmac.compare_digest(code_at(secret, step), code) and fresh:
            found = step
    return found


def secret_text(secret: bytes) -> str:
    """The secret as people type it into an authenticator app: base32, without padding."""
    return base64.b32encode(secret).decode().rstrip("=")


def provisioning_uri(secret: bytes, *, issuer: str, account: str) -> str:
    """The ``otpauth://`` link an authenticator app scans (the Key URI format)."""
    label = quote(f"{issuer}:{account}", safe="")
    query = urlencode(
        {
            "secret": secret_text(secret),
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": PERIOD_SECONDS,
        },
        quote_via=quote,
    )
    return f"otpauth://totp/{label}?{query}"
