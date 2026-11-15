"""Where a sign-in goes back to: a page of the web app, never another site (an open redirect)."""

import re
from typing import Final

MAX_LENGTH: Final = 512
# A path on the site: one slash, then no second slash or backslash (which browsers read as a
# host), no spaces and no control characters.
_PATH: Final = re.compile(r"/(?![/\\])[^\s\\\x00-\x1f\x7f]*")


def safe_return_path(raw: str | None) -> str | None:
    """``raw`` if it is a path on this site, else None."""
    if raw is None or len(raw) > MAX_LENGTH or _PATH.fullmatch(raw) is None:
        return None
    return raw
