"""The cookies the API sets: names and attributes in one place (ARCHITECTURE §12).

The session and CSRF cookies carry the ``__Secure-`` prefix, so browsers accept them only with the
Secure attribute and from a secure origin (https, or localhost in development); a page served over
plain http can't plant one. In production ``SESSION_COOKIE_DOMAIN`` names the parent domain, so the
web app and the API (``api.<domain>``) both receive them; locally they are host-only.

The staff login cookie is ``__Host-``: always host-only, so not even a sibling subdomain can plant
one. Every cookie is ``SameSite=Lax`` and ``Path=/``.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from starlette.responses import Response

# The opaque session token. HttpOnly: page scripts never see it.
SESSION_COOKIE: Final = "__Secure-session"
# The CSRF token (app/core/csrf.py). Readable by the web app, which echoes it in CSRF_HEADER.
CSRF_COOKIE: Final = "__Secure-csrf"
CSRF_HEADER: Final = "X-CSRF-Token"
# A Google sign-in in progress (step 1.3): the login id its state, nonce and PKCE verifier come
# from. HttpOnly, host-only and short-lived.
STAFF_LOGIN_COOKIE: Final = "__Host-staff-login"


@dataclass(frozen=True)
class CookiePolicy:
    """Where cookies apply: ``domain`` is the parent domain in production, None for host-only."""

    domain: str | None = None

    def set(
        self,
        response: Response,
        name: str,
        value: str,
        *,
        max_age: int,
        http_only: bool,
        host_only: bool = False,
    ) -> None:
        response.set_cookie(
            name,
            value,
            max_age=max_age,
            path="/",
            domain=None if host_only else self.domain,
            secure=True,
            httponly=http_only,
            samesite="lax",
        )

    def clear(
        self, response: Response, name: str, *, http_only: bool, host_only: bool = False
    ) -> None:
        response.delete_cookie(
            name,
            path="/",
            domain=None if host_only else self.domain,
            secure=True,
            httponly=http_only,
            samesite="lax",
        )
