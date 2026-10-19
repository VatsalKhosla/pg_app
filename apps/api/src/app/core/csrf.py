"""CSRF protection: signed double-submit tokens on every state-changing request (ARCHITECTURE §12).

``GET /v1/auth/csrf`` sets the CSRF cookie, which the web app reads and sends back in the
``X-CSRF-Token`` header on every POST, PUT, PATCH and DELETE. Another site can neither read the
cookie nor add the header, and the CORS allowlist keeps it from sending custom headers at all.

The token is also signed with ``SECRET_KEY`` and bound to the session cookie it was issued with
(OWASP's signed double-submit pattern). A cookie planted by a sibling subdomain, or left over
from an earlier session, therefore fails. Binding uses a hash of the session cookie, so the check
needs no database.

``require_csrf_token`` is a dependency of the whole application (app/main.py), so every route,
including ones added later, is protected without anyone remembering to protect it. It runs after
routing, so unknown routes and wrong methods still answer 404 and 405. Provider webhooks are the
only exemption: they carry no cookies and are verified by their signature instead.
"""

import base64
import hashlib
import hmac
import secrets
from typing import Final

from fastapi import Request  # noqa: TC002 (FastAPI resolves dependency signatures at runtime)

from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.errors import AppError

UNSAFE_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Signature-verified provider webhooks (ARCHITECTURE §9.3).
EXEMPT_PREFIXES: Final = ("/v1/webhooks/",)
# The token's lifetime as a cookie; the session it is bound to usually ends first.
CSRF_COOKIE_MAX_AGE: Final = 30 * 24 * 3600


class CsrfTokenInvalidError(AppError):
    status = 403
    code = "CSRF_TOKEN_INVALID"
    title = "Missing or invalid CSRF token"


def _signature(secret: bytes, session_token: str | None, nonce: str) -> str:
    binding = hashlib.sha256(session_token.encode()).hexdigest() if session_token else "none"
    message = b"csrf\x00" + binding.encode() + b"\x00" + nonce.encode()
    digest = hmac.new(secret, message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def issue_csrf_token(secret: bytes, session_token: str | None) -> str:
    """A new token bound to ``session_token`` (the session cookie's value), or to no session."""
    nonce = secrets.token_urlsafe(32)
    return f"{nonce}.{_signature(secret, session_token, nonce)}"


def is_valid_csrf_token(secret: bytes, token: str, session_token: str | None) -> bool:
    nonce, separator, signature = token.partition(".")
    if not (nonce and separator and signature):
        return False
    expected = _signature(secret, session_token, nonce)
    return hmac.compare_digest(signature.encode(), expected.encode())


def require_csrf_token(request: Request) -> None:
    """Refuse an unsafe request whose X-CSRF-Token header doesn't match a valid CSRF cookie."""
    if request.method not in UNSAFE_METHODS or request.url.path.startswith(EXEMPT_PREFIXES):
        return
    secret: bytes = request.app.state.csrf_secret
    sent = request.headers.get(CSRF_HEADER, "")
    stored = request.cookies.get(CSRF_COOKIE, "")
    if not (
        sent
        and hmac.compare_digest(sent.encode(), stored.encode())
        and is_valid_csrf_token(secret, sent, request.cookies.get(SESSION_COOKIE))
    ):
        raise CsrfTokenInvalidError(
            f"Send the {CSRF_COOKIE} cookie's value in the {CSRF_HEADER} header."
        )
