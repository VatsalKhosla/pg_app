"""Keyed digests: stable pseudonyms for personal data that must be looked up but never stored.

Rate-limit keys, for example, need "the same phone number" without keeping the number in Redis.
An unkeyed hash of a 10-digit phone number can be reversed by trying every number, so the digest
is an HMAC under the server's secret key, with a purpose string so digests made for different
uses never match.
"""

import hashlib
import hmac


def keyed_digest(secret: bytes, *, purpose: str, value: str) -> str:
    message = purpose.encode() + b"\x00" + value.encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]
