"""The browser's side of a Google sign-in, for staff (step 1.3) and for everyone (ADR 0068).

A sign-in keeps no server state. A random login id goes into a short-lived host-only cookie, and
the state, nonce and PKCE verifier are HMACs of it under SECRET_KEY: only the browser that started
a sign-in can finish it, and nothing about one sign-in helps with another. What a sign-in carries
to its end (a person's consent, the page to go back to) is part of the login id, so changing it
changes the state, and the sign-in fails.
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from datetime import datetime

# A Google sign-in must be finished within this long of starting it.
LOGIN_TTL: Final = timedelta(minutes=10)
_CLOCK_SKEW: Final = timedelta(minutes=1)


@dataclass(frozen=True)
class GoogleLogin:
    """A Google sign-in to start: the login cookie's value, and where to send the browser."""

    cookie: str
    authorization_url: str


@dataclass(frozen=True)
class LoginSecrets:
    state: str
    nonce: str
    code_verifier: str

    @property
    def code_challenge(self) -> str:
        return _b64(hashlib.sha256(self.code_verifier.encode()).digest())


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _derive(secret: bytes, purpose: str, value: str) -> str:
    return _b64(hmac.new(secret, f"{purpose}\x00{value}".encode(), hashlib.sha256).digest())


def new_login_id(now: datetime, *carried: str) -> str:
    """A fresh login id: 43 random characters, when it was issued, and what the sign-in carries."""
    return ".".join([secrets.token_urlsafe(32), str(int(now.timestamp())), *carried])


def login_secrets(secret: bytes, login_id: str, *, kind: str) -> LoginSecrets:
    """The state, nonce and PKCE verifier of a sign-in of ``kind`` ("staff" or "people"): a login
    id of one kind is no use for the other. 43 characters each, a valid PKCE verifier (RFC 7636
    asks for 43 to 128)."""
    return LoginSecrets(
        state=_derive(secret, f"{kind}-login-state", login_id),
        nonce=_derive(secret, f"{kind}-login-nonce", login_id),
        code_verifier=_derive(secret, f"{kind}-login-pkce", login_id),
    )


def login_is_fresh(issued: int, now: datetime) -> bool:
    """Whether a sign-in issued at ``issued`` (Unix seconds) may still be finished."""
    age = now.timestamp() - issued
    return -_CLOCK_SKEW.total_seconds() <= age <= LOGIN_TTL.total_seconds()


def same_state(expected: str, given: str | None) -> bool:
    return given is not None and hmac.compare_digest(expected, given)
