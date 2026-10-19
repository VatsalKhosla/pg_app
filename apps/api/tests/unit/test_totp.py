from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.identity.domain.totp import (
    DIGITS,
    code_at,
    matching_step,
    provisioning_uri,
    secret_text,
    time_step,
)

# RFC 6238, Appendix B: the SHA-1 test key and its eight-digit codes at these times.
RFC_SECRET = b"12345678901234567890"
NOW = datetime(2027, 7, 14, 10, 0, 5, tzinfo=UTC)
SECRET = bytes(range(20))


@pytest.mark.parametrize(
    ("unix_time", "code"),
    [
        (59, "94287082"),
        (1_111_111_109, "07081804"),
        (1_111_111_111, "14050471"),
        (1_234_567_890, "89005924"),
        (2_000_000_000, "69279037"),
        (20_000_000_000, "65353130"),
    ],
)
def test_codes_match_the_rfcs_test_vectors(unix_time: int, code: str) -> None:
    step = time_step(datetime.fromtimestamp(unix_time, tz=UTC))

    assert code_at(RFC_SECRET, step, digits=8) == code
    # Six-digit codes are the same number's last six digits.
    assert code_at(RFC_SECRET, step) == code[-6:]


def _code(steps_from_now: int) -> str:
    return code_at(SECRET, time_step(NOW) + steps_from_now)


def test_a_code_counts_for_its_own_step_and_one_either_side() -> None:
    current = time_step(NOW)

    def step_of(code: str) -> int | None:
        return matching_step(SECRET, code, now=NOW, last_used_step=None)

    assert [step_of(_code(offset)) for offset in (-1, 0, 1)] == [current - 1, current, current + 1]
    assert step_of(_code(-2)) is None
    assert step_of(_code(2)) is None


def test_each_code_works_once_and_never_after_a_newer_one() -> None:
    current = time_step(NOW)

    def step_of(code: str) -> int | None:
        return matching_step(SECRET, code, now=NOW, last_used_step=current)

    assert step_of(_code(0)) is None
    assert step_of(_code(-1)) is None
    assert step_of(_code(1)) == current + 1


@pytest.mark.parametrize(
    "code",
    ["", "12345", "1234567", "12345a", " 12345", "١٢٣٤٥٦"],
    ids=["empty", "short", "long", "letter", "space", "arabic-indic-digits"],
)
def test_anything_but_six_ascii_digits_is_refused(code: str) -> None:
    assert matching_step(SECRET, code, now=NOW, last_used_step=None) is None


@given(st.binary(min_size=20, max_size=20), st.integers(min_value=0, max_value=2**40))
def test_every_code_is_six_digits(secret: bytes, step: int) -> None:
    code = code_at(secret, step)

    assert len(code) == DIGITS
    assert code.isascii()
    assert code.isdigit()


def test_the_setup_link_is_the_one_authenticator_apps_read() -> None:
    uri = provisioning_uri(SECRET, issuer="Example staff", account="ops@example.in")

    parts = urlsplit(uri)
    assert (parts.scheme, parts.netloc) == ("otpauth", "totp")
    assert unquote(parts.path) == "/Example staff:ops@example.in"
    assert parse_qs(parts.query) == {
        "secret": [secret_text(SECRET)],
        "issuer": ["Example staff"],
        "algorithm": ["SHA1"],
        "digits": ["6"],
        "period": ["30"],
    }
    # Spaces as %20 (some apps misread "+"), and base32 without padding.
    assert "+" not in uri
    assert "=" not in secret_text(SECRET)
