"""Feature flag declarations, idempotency headers and the rate limiter's failure modes, without
a database or Redis."""

from collections.abc import Callable
from datetime import timedelta
from typing import Annotated

import httpx
import pytest
from fastapi import Depends

from app.config import Settings
from app.core.flags import FLAGS, Flag
from app.core.idempotency import fingerprint, idempotency_key
from app.core.ratelimit import RateLimit, RateLimitedError, rate_limited
from app.main import create_app

type Requester = Callable[..., httpx.Response]
type SettingsFactory = Callable[..., Settings]


def test_every_flag_is_declared_with_a_valid_default() -> None:
    assert set(FLAGS) == set(Flag)
    assert all(spec.accepts(spec.default) and spec.description for spec in FLAGS.values())


def test_flag_defaults_match_the_product_context() -> None:
    # PRODUCT_CONTEXT §9: contacts hidden pending legal advice, token as a payment until Razorpay
    # enables mandates, and everything later-phase off.
    defaults = {flag: spec.default for flag, spec in FLAGS.items()}

    assert defaults.pop(Flag.HIDE_OWNER_CONTACT) is True
    assert defaults.pop(Flag.TOKEN_MODE) == "payment"
    assert set(defaults.values()) == {False}


def test_choice_flags_accept_only_their_choices() -> None:
    spec = FLAGS[Flag.TOKEN_MODE]

    assert spec.accepts("upi_mandate")
    assert not spec.accepts("cash")
    assert not spec.accepts(True)


def test_fingerprints_change_with_method_route_and_body() -> None:
    base = fingerprint("POST", "/v1/bookings", b'{"quoteId":"q1"}')

    assert base == fingerprint("POST", "/v1/bookings", b'{"quoteId":"q1"}')
    assert base != fingerprint("PUT", "/v1/bookings", b'{"quoteId":"q1"}')
    assert base != fingerprint("POST", "/v1/payments", b'{"quoteId":"q1"}')
    assert base != fingerprint("POST", "/v1/bookings", b'{"quoteId":"q2"}')
    # Length-prefixed parts: shifting bytes between parts can't produce the same digest.
    assert fingerprint("POST", "/v1/a", b"b") != fingerprint("POST", "/v1/", b"ab")


@pytest.mark.parametrize(
    ("headers", "code"),
    [({}, "IDEMPOTENCY_KEY_REQUIRED"), ({"Idempotency-Key": "short"}, "IDEMPOTENCY_KEY_INVALID")],
)
def test_idempotent_routes_need_a_well_formed_key(
    make_settings: SettingsFactory,
    request_app: Requester,
    csrf_headers: dict[str, str],
    headers: dict[str, str],
    code: str,
) -> None:
    app = create_app(make_settings())

    @app.post("/test/create")
    async def create(key: Annotated[str, Depends(idempotency_key)]) -> dict[str, str]:
        return {"key": key}

    response = request_app(app, "POST", "/test/create", headers={**csrf_headers, **headers})

    assert response.status_code == 400
    assert response.json()["code"] == code


def test_rate_limited_errors_say_when_to_retry() -> None:
    error = RateLimitedError(timedelta(seconds=12, milliseconds=1))

    assert error.status == 429
    assert error.headers == {"Retry-After": "13"}


@pytest.mark.parametrize(("fail_open", "status_code"), [(True, 200), (False, 503)])
def test_an_unreachable_redis_fails_open_or_closed_as_configured(
    make_settings: SettingsFactory, request_app: Requester, fail_open: bool, status_code: int
) -> None:
    # The test settings point Redis at a port where nothing listens.
    app = create_app(make_settings())
    rule = RateLimit("test.limited", limit=5, window=timedelta(minutes=1), fail_open=fail_open)

    @app.get("/test/limited", dependencies=[Depends(rate_limited(rule))])
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    assert request_app(app, "GET", "/test/limited").status_code == status_code


def test_rate_limits_need_a_sensible_size() -> None:
    with pytest.raises(ValueError, match="limit >= 1"):
        RateLimit("test.bad", limit=0, window=timedelta(minutes=1))
