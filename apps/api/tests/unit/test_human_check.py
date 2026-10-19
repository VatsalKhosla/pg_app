import asyncio
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import SecretStr

from app.core.errors import ServiceUnavailableError
from app.core.human_check import (
    MAX_TOKEN_LENGTH,
    SITEVERIFY_URL,
    DisabledHumanCheck,
    TurnstileCheck,
)

SECRET = SecretStr("turnstile-secret")
SITE = "pg.example"
ACTION = "otp_request"
SOLVED = {"success": True, "action": ACTION, "hostname": SITE}
WIDGET_TOKEN = "token-from-widget"


def _turnstile(
    respond: Callable[[httpx.Request], httpx.Response],
) -> tuple[TurnstileCheck, list[dict[str, list[str]]]]:
    sent: list[dict[str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == SITEVERIFY_URL
        sent.append(parse_qs(request.content.decode()))
        return respond(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TurnstileCheck(http, SECRET, hostnames=frozenset({SITE})), sent


def _answer(body: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _: httpx.Response(200, json=body)


def _verify(
    check: TurnstileCheck, token: str = WIDGET_TOKEN, *, remote_ip: str | None = None
) -> bool:
    return asyncio.run(check.verify(token, remote_ip=remote_ip, action=ACTION))


def test_a_solved_challenge_passes_with_the_secret_token_and_ip() -> None:
    check, sent = _turnstile(_answer(SOLVED))

    assert _verify(check, remote_ip="203.0.113.7")

    assert sent[0]["secret"] == ["turnstile-secret"]
    assert sent[0]["response"] == ["token-from-widget"]
    assert sent[0]["remoteip"] == ["203.0.113.7"]
    assert len(sent[0]["idempotency_key"][0]) == 36


def test_a_refused_or_replayed_token_fails() -> None:
    check, _ = _turnstile(_answer({"success": False, "error-codes": ["timeout-or-duplicate"]}))

    assert not _verify(check, "used-token")


@pytest.mark.parametrize(
    "solved_elsewhere",
    [
        {"action": "visit_request"},
        {"action": None},
        {"hostname": "copy-of-the-site.example"},
        {"hostname": None},
    ],
    ids=["another-form", "no-form", "another-site", "no-site"],
)
def test_a_token_solved_for_another_form_or_site_fails(solved_elsewhere: dict[str, Any]) -> None:
    check, _ = _turnstile(_answer(SOLVED | solved_elsewhere))

    assert not _verify(check)


def test_cloudflares_test_keys_pass_without_a_form_or_site() -> None:
    # What siteverify answers for the always-pass test secret (checked against Cloudflare).
    check, _ = _turnstile(
        _answer(
            {
                "success": True,
                "error-codes": [],
                "challenge_ts": "2026-10-19T11:05:36.827Z",
                "hostname": "example.com",
                "metadata": {"result_with_testing_key": True},
            }
        )
    )

    assert _verify(check)


def test_a_refused_secret_key_is_our_fault_not_the_visitors() -> None:
    check, _ = _turnstile(_answer({"success": False, "error-codes": ["invalid-input-secret"]}))

    with pytest.raises(ServiceUnavailableError):
        _verify(check)


@pytest.mark.parametrize("token", ["", "x" * (MAX_TOKEN_LENGTH + 1)], ids=["empty", "oversized"])
def test_empty_or_oversized_tokens_fail_without_asking_cloudflare(token: str) -> None:
    check, sent = _turnstile(_answer(SOLVED))

    assert not _verify(check, token)
    assert sent == []


@pytest.mark.parametrize(
    "trouble",
    [
        lambda: httpx.Response(503),
        lambda: httpx.Response(200, json={"success": False, "error-codes": ["internal-error"]}),
        lambda: httpx.Response(200, text="<html>Bad gateway</html>"),
    ],
    ids=["server-error", "internal-error", "not-json"],
)
def test_cloudflare_trouble_is_retried_with_the_same_idempotency_key(
    trouble: Callable[[], httpx.Response],
) -> None:
    responses = iter([trouble(), trouble(), httpx.Response(200, json=SOLVED)])
    check, sent = _turnstile(lambda _: next(responses))

    assert _verify(check)
    assert len(sent) == 3
    assert len({attempt["idempotency_key"][0] for attempt in sent}) == 1


def test_an_unreachable_cloudflare_refuses_rather_than_letting_bots_in() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    check, _ = _turnstile(unreachable)

    with pytest.raises(ServiceUnavailableError):
        _verify(check)


def test_the_disabled_check_lets_everything_through() -> None:
    assert asyncio.run(DisabledHumanCheck().verify("", remote_ip=None, action=ACTION))
