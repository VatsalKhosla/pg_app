"""The Google adapter against a stand-in for Google's endpoints, with ID tokens signed by a test key
in the shapes Google's documentation and discovery document give."""

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import SecretStr

from app.core.clock import FrozenClock
from app.core.errors import ServiceUnavailableError
from app.modules.identity.adapters.google_oidc import (
    AUTHORIZATION_ENDPOINT,
    KEYS_ENDPOINT,
    TOKEN_ENDPOINT,
    GoogleOidc,
)
from app.modules.identity.domain.staff import GoogleAccount
from app.modules.identity.errors import StaffSignInExpiredError

CLIENT_ID = "1234-test.apps.googleusercontent.com"
REDIRECT_URI = "https://api.example.in/v1/auth/staff/google/callback"
NOW = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)
NONCE = "nonce-of-this-sign-in"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, str]:
    numbers = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": kid,
        "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8)),
        "e": _b64(numbers.e.to_bytes(3)),
    }


def _claims(**changes: Any) -> dict[str, Any]:
    claims = {
        "iss": "https://accounts.google.com",
        "azp": CLIENT_ID,
        "aud": CLIENT_ID,
        "sub": "110169484474386276334",
        "hd": "example.in",
        "email": "ops@example.in",
        "email_verified": True,
        "nonce": NONCE,
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
    }
    claims.update(changes)
    return {name: value for name, value in claims.items() if value is not None}


def _id_token(
    claims: dict[str, Any] | None = None,
    *,
    key: rsa.RSAPrivateKey = KEY,
    kid: str = "key-1",
    alg: str = "RS256",
) -> str:
    header = _b64(json.dumps({"alg": alg, "kid": kid, "typ": "JWT"}).encode())
    payload = _b64(json.dumps(claims or _claims()).encode())
    signature = key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64(signature)}"


class Google:
    """Google's token and keys endpoints, answering as the test sets them up."""

    def __init__(self) -> None:
        self.id_token = _id_token()
        self.token_response: httpx.Response | None = None
        self.keys = [_jwk(KEY, "key-1")]
        self.keys_up = True
        self.token_requests: list[dict[str, list[str]]] = []
        self.keys_fetches = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_ENDPOINT:
            self.token_requests.append(parse_qs(request.content.decode()))
            if self.token_response is not None:
                return self.token_response
            return httpx.Response(200, json={"id_token": self.id_token, "token_type": "Bearer"})
        assert str(request.url) == KEYS_ENDPOINT
        self.keys_fetches += 1
        if not self.keys_up:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={"keys": self.keys},
            headers={"Cache-Control": "public, max-age=3600, must-revalidate, no-transform"},
        )


@pytest.fixture
def google() -> Google:
    return Google()


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


@pytest.fixture
def adapter(google: Google, clock: FrozenClock) -> GoogleOidc:
    return GoogleOidc(
        httpx.AsyncClient(transport=httpx.MockTransport(google)),
        client_id=CLIENT_ID,
        client_secret=SecretStr("client-secret"),
        redirect_uri=REDIRECT_URI,
        clock=clock,
    )


def _finish(adapter: GoogleOidc, *, nonce: str = NONCE) -> GoogleAccount:
    return asyncio.run(adapter.finish("code-from-google", code_verifier="verifier", nonce=nonce))


def test_the_sign_in_asks_google_for_a_code_with_pkce_and_a_nonce(adapter: GoogleOidc) -> None:
    url = adapter.authorization_url(state="state", nonce=NONCE, code_challenge="challenge")

    assert url.startswith(AUTHORIZATION_ENDPOINT + "?")
    assert parse_qs(urlsplit(url).query) == {
        "client_id": [CLIENT_ID],
        "response_type": ["code"],
        "scope": ["openid email"],
        "redirect_uri": [REDIRECT_URI],
        "state": ["state"],
        "nonce": [NONCE],
        "code_challenge": ["challenge"],
        "code_challenge_method": ["S256"],
        "prompt": ["select_account"],
    }


def test_one_workspace_domain_narrows_googles_account_chooser(
    google: Google, clock: FrozenClock
) -> None:
    adapter = GoogleOidc(
        httpx.AsyncClient(transport=httpx.MockTransport(google)),
        client_id=CLIENT_ID,
        client_secret=SecretStr("client-secret"),
        redirect_uri=REDIRECT_URI,
        clock=clock,
        hosted_domain="example.in",
    )

    url = adapter.authorization_url(state="state", nonce=NONCE, code_challenge="challenge")

    assert parse_qs(urlsplit(url).query)["hd"] == ["example.in"]


def test_a_valid_token_names_the_account(adapter: GoogleOidc, google: Google) -> None:
    account = _finish(adapter)

    assert account == GoogleAccount(
        subject="110169484474386276334",
        email="ops@example.in",
        email_verified=True,
        hosted_domain="example.in",
    )
    assert google.token_requests == [
        {
            "code": ["code-from-google"],
            "client_id": [CLIENT_ID],
            "client_secret": ["client-secret"],
            "redirect_uri": [REDIRECT_URI],
            "grant_type": ["authorization_code"],
            "code_verifier": ["verifier"],
        }
    ]


def test_a_used_or_expired_code_means_starting_again(adapter: GoogleOidc, google: Google) -> None:
    google.token_response = httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(StaffSignInExpiredError):
        _finish(adapter)


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(401, json={"error": "invalid_client"}),
        httpx.Response(500, text="<html>"),
        httpx.Response(200, json={"access_token": "no-id-token"}),
    ],
    ids=["wrong-client-secret", "google-down", "no-id-token"],
)
def test_other_answers_from_the_token_endpoint_are_service_trouble(
    adapter: GoogleOidc, google: Google, answer: httpx.Response
) -> None:
    google.token_response = answer

    with pytest.raises(ServiceUnavailableError):
        _finish(adapter)


def test_an_unreachable_google_is_service_trouble(clock: FrozenClock) -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    adapter = GoogleOidc(
        httpx.AsyncClient(transport=httpx.MockTransport(unreachable)),
        client_id=CLIENT_ID,
        client_secret=SecretStr("client-secret"),
        redirect_uri=REDIRECT_URI,
        clock=clock,
    )

    with pytest.raises(ServiceUnavailableError):
        _finish(adapter)


def _unsigned(alg: str) -> str:
    header = _b64(json.dumps({"alg": alg, "kid": "key-1"}).encode())
    return f"{header}.{_b64(json.dumps(_claims()).encode())}."


@pytest.mark.parametrize(
    "token",
    [
        _id_token(key=OTHER_KEY),
        _unsigned("none"),
        _unsigned("HS256"),
        _id_token(kid="key-nobody-published"),
        _id_token(_claims(iss="https://accounts.google.com.evil.example")),
        _id_token(_claims(aud="another-client.apps.googleusercontent.com", azp=None)),
        _id_token(_claims(azp="another-client.apps.googleusercontent.com")),
        _id_token(_claims(aud=[CLIENT_ID, "another-client"], azp=None)),
        _id_token(_claims(sub=None)),
        "not-a-jwt",
    ],
    ids=[
        "signed-by-another-key",
        "alg-none",
        "alg-hs256",
        "unknown-key",
        "another-issuer",
        "another-audience",
        "another-authorized-party",
        "several-audiences-without-azp",
        "no-subject",
        "not-a-jwt",
    ],
)
def test_a_token_failing_a_check_is_refused(
    adapter: GoogleOidc, google: Google, token: str
) -> None:
    google.id_token = token

    with pytest.raises(ServiceUnavailableError):
        _finish(adapter)


def test_the_short_issuer_google_also_uses_is_accepted(adapter: GoogleOidc, google: Google) -> None:
    google.id_token = _id_token(_claims(iss="accounts.google.com"))

    assert _finish(adapter).subject == "110169484474386276334"


@pytest.mark.parametrize(
    "claims",
    [
        _claims(nonce="nonce-of-another-sign-in"),
        _claims(nonce=None),
        _claims(exp=int((NOW - timedelta(seconds=1)).timestamp())),
    ],
    ids=["another-sign-ins-nonce", "no-nonce", "expired"],
)
def test_a_token_from_another_sign_in_or_past_its_expiry_means_starting_again(
    adapter: GoogleOidc, google: Google, claims: dict[str, Any]
) -> None:
    google.id_token = _id_token(claims)

    with pytest.raises(StaffSignInExpiredError):
        _finish(adapter)


def _long_lived_token() -> str:
    """A token still valid after the clock moves on by hours."""
    return _id_token(_claims(exp=int((NOW + timedelta(days=1)).timestamp())))


def test_googles_keys_are_kept_as_long_as_google_says(
    adapter: GoogleOidc, google: Google, clock: FrozenClock
) -> None:
    google.id_token = _long_lived_token()
    _finish(adapter)
    clock.advance(timedelta(minutes=59))
    _finish(adapter)
    assert google.keys_fetches == 1

    clock.advance(timedelta(minutes=2))
    _finish(adapter)
    assert google.keys_fetches == 2


def test_a_new_key_is_fetched_but_not_more_than_once_a_minute(
    adapter: GoogleOidc, google: Google, clock: FrozenClock
) -> None:
    _finish(adapter)
    google.keys = [_jwk(KEY, "key-1"), _jwk(OTHER_KEY, "key-2")]
    google.id_token = _id_token(key=OTHER_KEY, kid="key-2")

    with pytest.raises(ServiceUnavailableError):
        # Within a minute of the last fetch: the new key isn't looked for yet.
        _finish(adapter)
    clock.advance(timedelta(minutes=1))
    _finish(adapter)

    assert google.keys_fetches == 2


def test_known_keys_keep_working_while_google_cant_be_reached(
    adapter: GoogleOidc, google: Google, clock: FrozenClock
) -> None:
    google.id_token = _long_lived_token()
    _finish(adapter)
    google.keys_up = False
    clock.advance(timedelta(hours=2))

    assert _finish(adapter).subject == "110169484474386276334"
