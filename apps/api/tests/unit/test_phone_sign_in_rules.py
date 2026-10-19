import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.logging import configure_logging
from app.modules.identity.adapters.console_otp import ConsoleOtpSender
from app.modules.identity.domain.otp import (
    CODE_TTL,
    MAX_ATTEMPTS,
    ChallengeState,
    attempts_left,
    challenge_state,
    resend_wait,
)
from app.modules.identity.domain.phones import normalize_indian_mobile

NOW = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "written",
    [
        "9876543210",
        "98765 43210",
        "98765-43210",
        "(98765) 43210",
        "+919876543210",
        "+91 98765 43210",
        "+91-98765-43210",
        "919876543210",
        "09876543210",
        "0091 98765 43210",
    ],
)
def test_the_usual_ways_of_writing_a_mobile_number_become_e164(written: str) -> None:
    assert normalize_indian_mobile(written) == "+919876543210"


@pytest.mark.parametrize(
    "written",
    [
        "",
        "5876543210",  # landlines and other ranges, not mobiles
        "987654321",  # nine digits
        "98765432101",  # eleven digits without a leading 0
        "+14155550123",  # not Indian
        "+92 300 1234567",
        "98765 4321O",  # a letter O
        "९८७६५४३२१०",  # Devanagari digits: valid characters, but not what SMS gateways take
        "+91 +91 98765 43210",
    ],
)
def test_anything_else_is_refused(written: str) -> None:
    assert normalize_indian_mobile(written) is None


mobiles = st.from_regex(r"[6-9][0-9]{9}", fullmatch=True)


@given(mobiles, st.sampled_from(["", "+91", "91", "0", "0091", "+91 ", "+91-"]))
def test_every_mobile_number_survives_any_common_prefix(mobile: str, prefix: str) -> None:
    assert normalize_indian_mobile(prefix + mobile) == "+91" + mobile


@given(st.text(max_size=20))
def test_normalising_twice_changes_nothing(raw: str) -> None:
    once = normalize_indian_mobile(raw)
    if once is not None:
        assert normalize_indian_mobile(once) == once


def test_an_open_challenge_locks_after_five_wrong_tries() -> None:
    def state(attempts: int) -> ChallengeState:
        return challenge_state(
            now=NOW,
            expires_at=NOW + CODE_TTL,
            attempts=attempts,
            consumed_at=None,
            superseded_at=None,
        )

    assert [state(attempts) for attempts in range(MAX_ATTEMPTS + 1)] == [
        *[ChallengeState.OPEN] * MAX_ATTEMPTS,
        ChallengeState.LOCKED,
    ]
    assert attempts_left(0) == MAX_ATTEMPTS
    assert attempts_left(MAX_ATTEMPTS + 1) == 0


def test_a_used_or_replaced_challenge_is_used_and_an_old_one_expires() -> None:
    def state(
        *,
        now: datetime = NOW,
        consumed_at: datetime | None = None,
        superseded_at: datetime | None = None,
    ) -> ChallengeState:
        return challenge_state(
            now=now,
            expires_at=NOW + CODE_TTL,
            attempts=0,
            consumed_at=consumed_at,
            superseded_at=superseded_at,
        )

    assert state(consumed_at=NOW) == ChallengeState.USED
    assert state(superseded_at=NOW) == ChallengeState.USED
    assert state(now=NOW + CODE_TTL) == ChallengeState.EXPIRED


def test_a_new_code_may_follow_30_seconds_after_the_last() -> None:
    assert resend_wait(now=NOW, last_requested_at=None) == timedelta(0)
    assert resend_wait(now=NOW, last_requested_at=NOW - timedelta(seconds=10)) == timedelta(
        seconds=20
    )
    assert resend_wait(now=NOW, last_requested_at=NOW - timedelta(seconds=30)) == timedelta(0)


def test_the_development_sender_logs_the_code_with_the_phone_masked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", fmt="json")

    asyncio.run(ConsoleOtpSender().send("+919876543210", "123456"))

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["code"] == "123456"
    assert line["phone"] == "******3210"
