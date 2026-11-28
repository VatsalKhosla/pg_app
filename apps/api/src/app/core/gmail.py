"""Email through Gmail's API (ADR 0074), for a host that blocks SMTP's ports, as Render's free plan
does: HTTPS only.

A Google service account in the founders' Google Cloud project holds a key. The Workspace's
domain-wide delegation lets it act for the Workspace's users with one scope only, gmail.send.
The mailer signs a short-lived token (RS256, `cryptography`) saying it acts for the sending
address, trades it at Google's token endpoint for an access token, and posts each message to
Gmail, which sends it from that mailbox. Only the sending address is ever acted for.
"""

import base64
import json
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Final

import httpx
import structlog
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.clock import Clock, SystemClock
from app.core.pii import mask_email

logger = structlog.stdlib.get_logger(__name__)

GMAIL_SEND_SCOPE: Final = "https://www.googleapis.com/auth/gmail.send"
TOKEN_URL: Final = "https://oauth2.googleapis.com/token"  # noqa: S105 - an address, not a secret
SEND_URL: Final = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
JWT_BEARER: Final = "urn:ietf:params:oauth:grant-type:jwt-bearer"
# The longest Google allows a signed assertion to live, and how close to its end an access token
# is replaced rather than used.
ASSERTION_LIFETIME_S: Final = 3600
TOKEN_MARGIN_S: Final = 300
TIMEOUT: Final = httpx.Timeout(20.0, connect=5.0)

# What Google's refusals most often mean, for the log: the founders' setup steps, by Google's
# own error words.
_HINTS: Final = {
    "unauthorized_client": (
        "the Workspace admin console hasn't allowed this service account's client ID the gmail.send"
        " scope (Security, API controls, Domain-wide delegation)"
    ),
    "invalid_grant": "MAIL_FROM isn't a user of the Workspace, or the key was deleted",
    "accessNotConfigured": "the Gmail API isn't turned on in the service account's Cloud project",
    "SERVICE_DISABLED": "the Gmail API isn't turned on in the service account's Cloud project",
}


class GmailNotSentError(Exception):
    """Google refused the token or the message. The reason, never a secret."""


@dataclass(frozen=True, slots=True)
class ServiceAccountKey:
    """A Google service account's key, as its JSON file gives it."""

    client_email: str
    client_id: str
    private_key_id: str
    private_key: rsa.RSAPrivateKey = field(repr=False)


def parse_service_account_key(text: str) -> ServiceAccountKey | None:
    """The key in a service account's JSON file, as downloaded or as base64 of it; None if the
    text isn't one."""
    for candidate in (text.strip(), _unbase64(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            if not isinstance(data, dict) or data.get("type") != "service_account":
                continue
            private_key = serialization.load_pem_private_key(
                str(data["private_key"]).encode(), password=None
            )
            if not isinstance(private_key, rsa.RSAPrivateKey):
                continue
            return ServiceAccountKey(
                client_email=str(data["client_email"]),
                client_id=str(data["client_id"]),
                private_key_id=str(data["private_key_id"]),
                private_key=private_key,
            )
        except ValueError, KeyError, TypeError:
            continue
    return None


def _unbase64(text: str) -> str:
    try:
        return base64.b64decode("".join(text.split()), validate=True).decode()
    except ValueError:
        return ""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def signed_assertion(key: ServiceAccountKey, *, subject: str, now: int) -> str:
    """The service account's signed claim to act for `subject`, with gmail.send only (RFC 7523)."""
    header = {"alg": "RS256", "typ": "JWT", "kid": key.private_key_id}
    claims = {
        "iss": key.client_email,
        "sub": subject,
        "scope": GMAIL_SEND_SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + ASSERTION_LIFETIME_S,
    }
    signing_input = f"{_b64url(_json(header))}.{_b64url(_json(claims))}"
    signature = key.private_key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(signature)}"


def _reason(response: httpx.Response) -> str:
    """Google's own words for a refusal, and what they usually mean here."""
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        words = [body["error"], str(body.get("error_description", ""))]
    elif isinstance(body, dict) and isinstance(body.get("error"), dict):
        error = body["error"]
        items = [
            item
            for key in ("details", "errors")
            if isinstance(error.get(key), list)
            for item in error[key]
        ]
        details = [str(item.get("reason", "")) for item in items if isinstance(item, dict)]
        words = [str(error.get("status", "")), str(error.get("message", "")), *details]
    else:
        return f"HTTP {response.status_code}"
    said = "; ".join(word for word in words if word)
    hints = {hint for code, hint in _HINTS.items() if any(code in word for word in words)}
    return f"HTTP {response.status_code}: {said}" + "".join(f" ({hint})" for hint in sorted(hints))


class GmailApiMailer:
    """Sends each message from `sender`'s mailbox through Gmail's API, over HTTPS."""

    def __init__(
        self,
        *,
        key: ServiceAccountKey,
        sender: str,
        name: str,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._key = key
        self._sender = sender
        self._from = formataddr((name, sender))
        self._domain = sender.rpartition("@")[2]
        self._transport = transport
        self._clock = clock or SystemClock()
        self._token: str | None = None
        self._token_until = 0.0

    async def send(self, to: str, subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain=self._domain)
        message.set_content(text)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        async with httpx.AsyncClient(timeout=TIMEOUT, transport=self._transport) as http:
            response = await self._post(http, raw, fresh=False)
            if response.status_code == httpx.codes.UNAUTHORIZED:
                # The token ended or was revoked early: once more with a new one.
                response = await self._post(http, raw, fresh=True)
        if response.status_code != httpx.codes.OK:
            msg = f"Gmail didn't send the message: {_reason(response)}"
            raise GmailNotSentError(msg)
        logger.info("email sent", to=mask_email(to), subject=subject, via="gmail_api")

    async def _post(self, http: httpx.AsyncClient, raw: str, *, fresh: bool) -> httpx.Response:
        token = await self._access_token(http, fresh=fresh)
        return await http.post(
            SEND_URL, headers={"Authorization": f"Bearer {token}"}, json={"raw": raw}
        )

    async def _access_token(self, http: httpx.AsyncClient, *, fresh: bool) -> str:
        now = self._clock.now().timestamp()
        if not fresh and self._token is not None and now < self._token_until - TOKEN_MARGIN_S:
            return self._token
        assertion = signed_assertion(self._key, subject=self._sender, now=int(now))
        response = await http.post(
            TOKEN_URL, data={"grant_type": JWT_BEARER, "assertion": assertion}
        )
        if response.status_code != httpx.codes.OK:
            msg = f"Google didn't let the service account send: {_reason(response)}"
            raise GmailNotSentError(msg)
        body = response.json()
        self._token = str(body["access_token"])
        self._token_until = now + float(body.get("expires_in", ASSERTION_LIFETIME_S))
        return self._token
