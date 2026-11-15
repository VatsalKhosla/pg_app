"""Email addresses as accounts know them (ADR 0068): what a sign-in code may be sent to.

The rules are the common ones every mail provider accepts, a little stricter than the RFCs: a
dot-atom name (no quoted names or comments) at a domain name (no IP address), each part within
the RFC's length limits. An address is kept in lowercase. The database compares addresses
without regard to case (citext) anyway; lowercase keeps them looking the same everywhere.

An account's address is never something its person typed in unproven: it is one a code was sent
to and typed back, one Google says it has verified, or one staff entered (an owner's). So an
address on an account can be trusted to sign in to it.
"""

import re
from typing import Final

MAX_LENGTH: Final = 254
_MAX_NAME_LENGTH: Final = 64
_MAX_LABEL_LENGTH: Final = 63
# RFC 5322's atext, joined by single dots.
_NAME: Final = re.compile(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
# A label: letters, digits and inner hyphens. The last one (the top-level domain) has a letter.
_LABEL: Final = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?")
_TOP_LEVEL: Final = re.compile(r"[a-z]{2,63}|xn--[a-z0-9-]{1,59}")


def normalize_email(raw: str) -> str | None:
    """The address in lowercase, or None if ``raw`` isn't one an account may have."""
    address = raw.strip().lower()
    if len(address) > MAX_LENGTH or address.count("@") != 1:
        return None
    name, _, domain = address.partition("@")
    if len(name) > _MAX_NAME_LENGTH or _NAME.fullmatch(name) is None:
        return None
    *names, top_level = domain.split(".")
    if not names or _TOP_LEVEL.fullmatch(top_level) is None:
        return None
    for label in [*names, top_level]:
        if len(label) > _MAX_LABEL_LENGTH or _LABEL.fullmatch(label) is None:
            return None
    return address
