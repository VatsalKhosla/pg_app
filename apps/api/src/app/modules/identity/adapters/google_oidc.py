"""Staff sign-in with Google: OpenID Connect's authorization code flow with PKCE (step 1.3).

The endpoints are the ones Google's discovery document names
(https://accounts.google.com/.well-known/openid-configuration). The ID token comes straight from
Google's token endpoint over TLS, in exchange for our client secret, so Google says it can be
trusted as it is. It is checked anyway, as if it had come from anywhere, so this adapter stays
safe however a token reaches it:
- its RS256 signature, against Google's published keys (kept as long as Google allows);
- the issuer, the audience and the authorized party;
- the expiry and the nonce.
"""

import asyncio
import base64
import hmac
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Final
from urllib.parse import urlencode

import httpx
import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import BaseModel, Field, ValidationError

from app.core.errors import ServiceUnavailableError
from app.modules.identity.domain.staff import GoogleAccount
from app.modules.identity.errors import StaffSignInExpiredError

if TYPE_CHECKING:
    from datetime import datetime

    from pydantic import SecretStr

    from app.core.clock import Clock

AUTHORIZATION_ENDPOINT: Final = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT: Final = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL
KEYS_ENDPOINT: Final = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS: Final = frozenset({"https://accounts.google.com", "accounts.google.com"})
# The account's id and address are all staff sign-in needs: no name or photo (DPDP).
SCOPE: Final = "openid email"
_MIN_KEY_BITS: Final = 2048
# How long Google's keys are kept when its answer doesn't say, the longest they are kept whatever
# it says, and how soon a token signed with a key not seen yet may fetch them again.
_DEFAULT_KEYS_TTL: Final = timedelta(hours=1)
_MAX_KEYS_TTL: Final = timedelta(hours=24)
_REFETCH_INTERVAL: Final = timedelta(minutes=1)
_MAX_AGE: Final = re.compile(r"max-age=(\d+)")

logger = structlog.stdlib.get_logger(__name__)


class InvalidIdTokenError(Exception):
    """An ID token failing a check that only a misconfiguration or an attack would fail."""


class _TokenResponse(BaseModel):
    id_token: str


class _TokenError(BaseModel):
    error: str = Field(max_length=64)


class _Header(BaseModel):
    alg: str
    kid: str


class _Claims(BaseModel):
    iss: str
    aud: str | list[str]
    azp: str | None = None
    exp: int
    # "Unique among all Google Accounts and never reused", at most 255 ASCII characters.
    sub: str = Field(min_length=1, max_length=255)
    nonce: str | None = None
    email: str
    email_verified: bool
    hd: str | None = None


class _Jwk(BaseModel):
    kty: str
    kid: str
    n: str | None = None
    e: str | None = None
    alg: str | None = None
    use: str | None = None


class _Jwks(BaseModel):
    keys: list[_Jwk]


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _rsa_key(jwk: _Jwk) -> rsa.RSAPublicKey | None:
    """The RSA signing key a JWK describes, or None for anything else."""
    if jwk.kty != "RSA" or jwk.n is None or jwk.e is None:
        return None
    if jwk.use not in {None, "sig"} or jwk.alg not in {None, "RS256"}:
        return None
    try:
        numbers = rsa.RSAPublicNumbers(
            e=int.from_bytes(_b64decode(jwk.e)), n=int.from_bytes(_b64decode(jwk.n))
        )
        key = numbers.public_key()
    except ValueError:
        return None
    return key if key.key_size >= _MIN_KEY_BITS else None


def _keys_ttl(cache_control: str | None) -> timedelta:
    match = _MAX_AGE.search(cache_control or "")
    if match is None:
        return _DEFAULT_KEYS_TTL
    return min(timedelta(seconds=int(match.group(1))), _MAX_KEYS_TTL)


def _unavailable() -> ServiceUnavailableError:
    return ServiceUnavailableError("Signing in with Google isn't working right now.")


class GoogleOidc:
    """The real Google. ``hosted_domain`` narrows Google's account chooser to one Workspace domain;
    a convenience only, since anyone can change the request: the hd claim is what's checked."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        client_id: str,
        client_secret: SecretStr,
        redirect_uri: str,
        clock: Clock,
        hosted_domain: str | None = None,
    ) -> None:
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._clock = clock
        self._hosted_domain = hosted_domain
        self._keys: dict[str, rsa.RSAPublicKey] = {}
        self._keys_expire_at: datetime | None = None
        self._keys_fetched_at: datetime | None = None
        self._keys_lock = asyncio.Lock()

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "scope": SCOPE,
            "redirect_uri": self._redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        if self._hosted_domain is not None:
            params["hd"] = self._hosted_domain
        return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

    async def finish(self, code: str, *, code_verifier: str, nonce: str) -> GoogleAccount:
        id_token = await self._redeem(code, code_verifier)
        try:
            claims = await self._verified_claims(id_token)
        except InvalidIdTokenError as error:
            logger.error("Google ID token refused", reason=str(error))
            raise _unavailable() from None
        # A token for another sign-in (the nonce), or one too old to use, means starting again.
        if claims.nonce is None or not hmac.compare_digest(claims.nonce, nonce):
            raise StaffSignInExpiredError
        if claims.exp <= self._clock.now().timestamp():
            raise StaffSignInExpiredError
        return GoogleAccount(
            subject=claims.sub,
            email=claims.email,
            email_verified=claims.email_verified,
            hosted_domain=claims.hd,
        )

    async def _redeem(self, code: str, code_verifier: str) -> str:
        """The ID token for ``code``. Not retried: a code works once, so a retry after a lost
        answer would be refused anyway."""
        form = {
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret.get_secret_value(),
            "redirect_uri": self._redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }
        try:
            response = await self._http.post(TOKEN_ENDPOINT, data=form)
        except httpx.HTTPError as error:
            logger.warning("Google's token endpoint unreachable", error=str(error))
            raise _unavailable() from None
        if response.status_code != httpx.codes.OK:
            oauth_error = _oauth_error(response)
            # A used or expired code, or a verifier that doesn't match: start again.
            if oauth_error == "invalid_grant":
                raise StaffSignInExpiredError
            logger.error(
                "Google refused the code", status=response.status_code, oauth_error=oauth_error
            )
            raise _unavailable()
        try:
            return _TokenResponse.model_validate_json(response.content).id_token
        except ValidationError:
            logger.error("Google's token endpoint answered without an ID token")
            raise _unavailable() from None

    async def _verified_claims(self, token: str) -> _Claims:
        parts = token.split(".")
        if len(parts) != 3:
            msg = "not a JWT"
            raise InvalidIdTokenError(msg)
        header_part, payload_part, signature_part = parts
        try:
            header = _Header.model_validate_json(_b64decode(header_part))
            signature = _b64decode(signature_part)
        except ValueError as error:
            msg = "malformed header or signature"
            raise InvalidIdTokenError(msg) from error
        # Only RS256, whatever the token says ("none" and HS256 tricks included).
        if header.alg != "RS256":
            msg = f"algorithm {header.alg[:16]}"
            raise InvalidIdTokenError(msg)
        key = await self._key(header.kid)
        if key is None:
            msg = "unknown signing key"
            raise InvalidIdTokenError(msg)
        try:
            key.verify(
                signature,
                f"{header_part}.{payload_part}".encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature:
            msg = "bad signature"
            raise InvalidIdTokenError(msg) from None
        try:
            claims = _Claims.model_validate_json(_b64decode(payload_part))
        except ValueError as error:
            msg = "malformed claims"
            raise InvalidIdTokenError(msg) from error
        if claims.iss not in ISSUERS:
            msg = "issuer"
            raise InvalidIdTokenError(msg)
        audiences = [claims.aud] if isinstance(claims.aud, str) else claims.aud
        if self._client_id not in audiences:
            msg = "audience"
            raise InvalidIdTokenError(msg)
        # With several audiences, the authorized party must be us (OpenID Connect Core 3.1.3.7).
        if (claims.azp is not None or len(audiences) > 1) and claims.azp != self._client_id:
            msg = "authorized party"
            raise InvalidIdTokenError(msg)
        return claims

    async def _key(self, kid: str) -> rsa.RSAPublicKey | None:
        async with self._keys_lock:
            now = self._clock.now()
            stale = self._keys_expire_at is None or now >= self._keys_expire_at
            # Google publishes a new key before signing with it, so an unknown key id may mean
            # our copy is old: fetch again, but not more than once a minute.
            unseen = kid not in self._keys and (
                self._keys_fetched_at is None or now - self._keys_fetched_at >= _REFETCH_INTERVAL
            )
            if stale or unseen:
                await self._refresh(now)
            return self._keys.get(kid)

    async def _refresh(self, now: datetime) -> None:
        self._keys_fetched_at = now
        try:
            response = await self._http.get(KEYS_ENDPOINT)
            response.raise_for_status()
            jwks = _Jwks.model_validate_json(response.content)
        except (httpx.HTTPError, ValidationError) as error:
            logger.warning("Google's signing keys couldn't be fetched", error=str(error))
            if not self._keys:
                raise _unavailable() from None
            # Keep the keys we have (Google keeps old keys published for a while), and try
            # again in a minute.
            self._keys_expire_at = now + _REFETCH_INTERVAL
            return
        self._keys = {jwk.kid: key for jwk in jwks.keys if (key := _rsa_key(jwk)) is not None}
        self._keys_expire_at = now + _keys_ttl(response.headers.get("cache-control"))


def _oauth_error(response: httpx.Response) -> str | None:
    try:
        return _TokenError.model_validate_json(response.content).error
    except ValidationError:
        return None
