"""The rules behind signing in by email and with Google (ADR 0068): which addresses an account may
have, where a sign-in may go back to, how long codes last, what a Google login carries, and what
a sign-in email says."""

import asyncio

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.config import BRAND_NAME
from app.core.errors import ServiceUnavailableError
from app.modules.identity.adapters.email_codes import EmailCodes
from app.modules.identity.domain.consent import ConsentPurpose
from app.modules.identity.domain.emails import MAX_LENGTH, normalize_email
from app.modules.identity.domain.otp import CODE_TTL, EMAIL_CODE_TTL, Channel, Destination
from app.modules.identity.domain.return_paths import safe_return_path
from app.modules.identity.service.google import _Carried


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Student@Example.com", "student@example.com"),
        ("  first.last+pg@mail.example.co.in ", "first.last+pg@mail.example.co.in"),
        ("o'brien@example.com", "o'brien@example.com"),
        ("name@example.xn--p1ai", "name@example.xn--p1ai"),
        ("name@sub-domain.example.org", "name@sub-domain.example.org"),
    ],
)
def test_addresses_are_kept_in_lowercase(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "plain",
        "@example.com",
        "name@",
        "name@example",
        "name@@example.com",
        "two@at@example.com",
        "name.@example.com",
        ".name@example.com",
        "na..me@example.com",
        "na me@example.com",
        '"quoted"@example.com',
        "name@-example.com",
        "name@example-.com",
        "name@exa_mple.com",
        "name@[127.0.0.1]",
        "name@127.0.0.1",
        "name@example.c",
        "name@example.123",
        "a" * 65 + "@example.com",
        "name@" + "a" * 64 + ".com",
        "name@" + ".".join(["a" * 60] * 5) + ".com",
    ],
)
def test_anything_else_isnt_an_address(raw: str) -> None:
    assert normalize_email(raw) is None


@given(st.text(max_size=300))
def test_whatever_is_typed_an_address_comes_out_short_lowercase_and_stable(raw: str) -> None:
    address = normalize_email(raw)
    if address is not None:
        assert len(address) <= MAX_LENGTH
        assert address == address.lower() == address.strip()
        assert normalize_email(address) == address


@pytest.mark.parametrize(
    "path", ["/", "/account", "/pg/a-fictional-pg?moveIn=2027-08", "/search#map", "/a/b/c"]
)
def test_a_sign_in_goes_back_to_a_page_of_the_site(path: str) -> None:
    assert safe_return_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        None,
        "",
        "account",
        "//evil.example",
        "/\\evil.example",
        "https://evil.example/",
        "/with space",
        "/tab\there",
        "/new\nline",
        "/" + "a" * 512,
    ],
)
def test_never_to_another_site(path: str | None) -> None:
    assert safe_return_path(path) is None


def test_a_code_lasts_longer_in_an_inbox_than_on_a_phone() -> None:
    assert Destination(Channel.PHONE, "+919876543210").code_ttl == CODE_TTL
    assert Destination(Channel.EMAIL, "student@example.com").code_ttl == EMAIL_CODE_TTL
    assert EMAIL_CODE_TTL > CODE_TTL


def test_a_google_login_carries_its_consent_and_page_unchanged() -> None:
    carried = _Carried(
        notice="draft-2", purposes=(ConsentPurpose.ACCOUNT,), back="/pg/a-fictional-pg?x=1"
    )

    again = _Carried.decoded(carried.encoded())

    assert again == carried
    assert again is not None
    assert again.consent is not None
    assert again.consent.purposes == frozenset({ConsentPurpose.ACCOUNT})
    assert _Carried.decoded(_Carried().encoded()) == _Carried()
    assert _Carried().consent is None


@pytest.mark.parametrize("value", ["", "!!!", "e30", "eyJ4IjoxfQ", "bm90IGpzb24"])
def test_a_login_carrying_anything_else_is_refused(value: str) -> None:
    # "e30" is {} (valid, nothing carried); the others aren't JSON, or have unknown fields.
    decoded = _Carried.decoded(value)
    assert decoded is None or decoded == _Carried()


class RecordedMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append((to, subject, text))


def test_a_sign_in_email_says_the_code_how_long_it_lasts_and_what_to_do_if_unasked() -> None:
    mailer = RecordedMailer()
    codes = EmailCodes(
        mailer, shows_code=False, ttl=EMAIL_CODE_TTL, site_url="https://www.example.in"
    )

    asyncio.run(codes.send("student@example.com", "123456"))

    [(to, subject, text)] = mailer.sent
    assert to == "student@example.com"
    assert subject == f"Your {BRAND_NAME} sign-in code"
    assert "123456" in text
    assert "10 minutes" in text
    assert "ignore this email" in text
    assert text.endswith(f"{BRAND_NAME}\nhttps://www.example.in\n")
    assert codes.available


def test_without_a_mailer_codes_show_on_a_test_site_and_are_off_elsewhere() -> None:
    shown = EmailCodes(None, shows_code=True, ttl=EMAIL_CODE_TTL, site_url="https://x.example")
    off = EmailCodes(None, shows_code=False, ttl=EMAIL_CODE_TTL, site_url="https://x.example")

    asyncio.run(shown.send("student@example.com", "123456"))

    assert shown.available
    assert not off.available
    with pytest.raises(ServiceUnavailableError):
        asyncio.run(off.send("student@example.com", "123456"))
