"""Email through Gmail's API (ADR 0074): the service account's key as people paste it, the token
it signs, and messages sent over HTTPS, with Google's refusals explained. Google is a mock
transport; the key is made here and belongs to no account."""

import asyncio
import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from email.message import Message
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.config import Settings
from app.core.clock import FrozenClock
from app.core.gmail import (
    GMAIL_SEND_SCOPE,
    JWT_BEARER,
    SEND_URL,
    TOKEN_URL,
    GmailApiMailer,
    GmailNotSentError,
    ServiceAccountKey,
    parse_service_account_key,
    signed_assertion,
)
from app.messages import build_mailer

SENDER = "support@example.in"
NOW = 1_800_000_000


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def key_file(private_key: rsa.RSAPrivateKey) -> str:
    """A service account's JSON key, as Google's download gives it (fictional)."""
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "a-fictional-project",
            "private_key_id": "a1b2c3",
            "private_key": pem,
            "client_email": "mail@a-fictional-project.iam.gserviceaccount.com",
            "client_id": "100000000000000000001",
            "token_uri": TOKEN_URL,
        },
        indent=2,
    )


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def test_the_key_is_read_as_downloaded_flattened_or_base64(key_file: str) -> None:
    flattened = " ".join(key_file.split("\n"))
    encoded = base64.b64encode(key_file.encode()).decode()

    keys = [parse_service_account_key(text) for text in (key_file, flattened, encoded)]

    assert all(key is not None for key in keys)
    assert {key.client_id for key in keys if key is not None} == {"100000000000000000001"}
    # The private key never shows in a repr, so never in a log line or a traceback.
    assert "PRIVATE" not in repr(keys[0])


def test_anything_else_isnt_a_key(key_file: str) -> None:
    other = json.loads(key_file) | {"type": "authorized_user"}

    for text in ("", "not json", "{}", json.dumps(other), key_file.replace("PRIVATE KEY", "X")):
        assert parse_service_account_key(text) is None


def test_the_token_claims_gmail_send_only_for_the_sending_address(
    key_file: str, private_key: rsa.RSAPrivateKey
) -> None:
    key = parse_service_account_key(key_file)
    assert key is not None

    header, claims, signature = signed_assertion(key, subject=SENDER, now=NOW).split(".")

    assert json.loads(_b64decode(header)) == {"alg": "RS256", "typ": "JWT", "kid": "a1b2c3"}
    assert json.loads(_b64decode(claims)) == {
        "iss": "mail@a-fictional-project.iam.gserviceaccount.com",
        "sub": SENDER,
        "scope": GMAIL_SEND_SCOPE,
        "aud": TOKEN_URL,
        "iat": NOW,
        "exp": NOW + 3600,
    }
    private_key.public_key().verify(
        _b64decode(signature),
        f"{header}.{claims}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


class FakeGoogle:
    """Google's token endpoint and Gmail's send, as a mock transport: what was asked, in order."""

    def __init__(self, *, token: httpx.Response | None = None, sends: list[int] | None = None):
        self.token_response = token or httpx.Response(
            200, json={"access_token": "an-access-token", "expires_in": 3599}
        )
        self.send_statuses = list(sends or [200])
        self.tokens = 0
        self.sent: list[tuple[str, Message]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            form = dict(item.split("=", 1) for item in request.content.decode().split("&"))
            assert form["grant_type"] == JWT_BEARER.replace(":", "%3A")
            self.tokens += 1
            return self.token_response
        assert str(request.url) == SEND_URL
        raw = json.loads(request.content)["raw"]
        self.sent.append((request.headers["Authorization"], message_from_bytes(_b64decode(raw))))
        status = self.send_statuses.pop(0) if self.send_statuses else 200
        if status == 200:
            return httpx.Response(200, json={"id": "a-message-id"})
        return httpx.Response(status, json={"error": {"code": status, "status": "UNAUTHENTICATED"}})


def _mailer(key_file: str, google: FakeGoogle, clock: FrozenClock | None = None) -> GmailApiMailer:
    key = parse_service_account_key(key_file)
    assert isinstance(key, ServiceAccountKey)
    return GmailApiMailer(
        key=key,
        sender=SENDER,
        name="Fix Your Stay",
        transport=httpx.MockTransport(google),
        clock=clock or FrozenClock(datetime.fromtimestamp(NOW, UTC)),
    )


def test_a_message_goes_from_the_sending_address_with_one_token_for_many(
    key_file: str,
) -> None:
    google = FakeGoogle()
    mailer = _mailer(key_file, google)

    asyncio.run(mailer.send("student@example.com", "Your sign-in code", "123456"))
    asyncio.run(mailer.send("owner@example.com", "A booking", "Booking PG-1"))

    assert google.tokens == 1
    [(bearer, message), (_, second)] = google.sent
    assert bearer == "Bearer an-access-token"
    assert message["From"] == f"Fix Your Stay <{SENDER}>"
    assert (message["To"], message["Subject"]) == ("student@example.com", "Your sign-in code")
    assert message["Message-ID"].endswith("@example.in>")
    assert message.get_payload(decode=True) == b"123456\n"
    assert second["To"] == "owner@example.com"


def test_an_ending_token_is_replaced_and_a_refused_one_tried_once_more(key_file: str) -> None:
    google = FakeGoogle(sends=[200, 401, 200])
    clock = FrozenClock(datetime.fromtimestamp(NOW, UTC))
    mailer = _mailer(key_file, google, clock)

    asyncio.run(mailer.send("student@example.com", "One", "1"))
    # 3,400 s on, the token is within its last five minutes: a new one, which Gmail refuses
    # once (revoked, say); the next is used.
    clock.advance(timedelta(seconds=3400))
    asyncio.run(mailer.send("student@example.com", "Two", "2"))

    assert google.tokens == 3
    assert [message["Subject"] for _, message in google.sent] == ["One", "Two", "Two"]


@pytest.mark.parametrize(
    ("token", "sends", "says"),
    [
        (
            httpx.Response(
                401,
                json={
                    "error": "unauthorized_client",
                    "error_description": "Client is unauthorized to retrieve access tokens",
                },
            ),
            [],
            "Domain-wide delegation",
        ),
        (
            None,
            [403],
            "HTTP 403",
        ),
    ],
)
def test_googles_refusals_say_what_to_set_up(
    key_file: str, token: httpx.Response | None, sends: list[int], says: str
) -> None:
    mailer = _mailer(key_file, FakeGoogle(token=token, sends=sends))

    with pytest.raises(GmailNotSentError, match=says):
        asyncio.run(mailer.send("student@example.com", "A code", "123456"))


def test_a_disabled_gmail_api_is_named(key_file: str) -> None:
    refusal: dict[str, Any] = {
        "error": {
            "code": 403,
            "message": "Gmail API has not been used in project 1 before or it is disabled.",
            "status": "PERMISSION_DENIED",
            "details": [{"reason": "SERVICE_DISABLED"}],
        }
    }

    def google(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(200, json={"access_token": "a-token", "expires_in": 3599})
        return httpx.Response(403, json=refusal)

    key = parse_service_account_key(key_file)
    assert key is not None
    mailer = GmailApiMailer(
        key=key, sender=SENDER, name="Fix Your Stay", transport=httpx.MockTransport(google)
    )

    with pytest.raises(GmailNotSentError, match="Gmail API isn't turned on"):
        asyncio.run(mailer.send("student@example.com", "A code", "123456"))


def test_the_settings_choose_gmails_api_once_the_key_is_there(
    make_settings: Callable[..., Settings], key_file: str
) -> None:
    waiting = make_settings(mail_sender="gmail_api", mail_from=SENDER)
    wrong = make_settings(
        mail_sender="gmail_api", mail_from=SENDER, gmail_service_account="not a key"
    )
    ready = make_settings(mail_sender="gmail_api", mail_from=SENDER, gmail_service_account=key_file)

    assert (waiting.mail_missing, waiting.mail_sender_in_use) == (
        ["GMAIL_SERVICE_ACCOUNT"],
        "unavailable",
    )
    assert wrong.mail_missing == ["GMAIL_SERVICE_ACCOUNT"]
    assert (ready.mail_missing, ready.mail_sender_in_use) == ([], "gmail_api")
    assert isinstance(build_mailer(ready), GmailApiMailer)
    # The key never shows in the settings' repr.
    assert "PRIVATE KEY" not in repr(ready)
