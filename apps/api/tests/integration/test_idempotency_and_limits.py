import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response
from redis.asyncio import Redis

from app.config import Settings
from app.core.clock import ClockDep, FrozenClock
from app.core.db import DbSession
from app.core.idempotency import (
    REPLAYED_HEADER,
    IdempotencyKeyReusedError,
    IdempotentRequest,
    StoredResponse,
    begin,
    complete,
    fingerprint,
    idempotent_request,
    replay,
)
from app.core.ids import new_public_id
from app.core.ratelimit import RateLimit, RateLimiter, rate_limited
from app.main import create_app

if TYPE_CHECKING:
    from tests.integration.conftest import RunDb, Sessionmaker

pytestmark = pytest.mark.integration

type Requester = Callable[..., httpx.Response]
type SettingsFactory = Callable[..., Settings]

START = datetime(2027, 7, 1, 4, 30, tzinfo=UTC)


class _AbortError(Exception):
    pass


def _request(
    *, scope: str = "user:1", key: str | None = None, body: bytes = b"{}"
) -> IdempotentRequest:
    return IdempotentRequest(
        scope=scope,
        key=key or uuid.uuid4().hex,
        method="POST",
        route="/v1/test",
        fingerprint=fingerprint("POST", "/v1/test", body),
    )


async def _attempt(
    sessionmaker: Sessionmaker,
    request: IdempotentRequest,
    clock: FrozenClock,
    runs: list[int],
    *,
    fail: bool = False,
) -> StoredResponse:
    """One request: replay a stored response, or do the work (counted in ``runs``) once."""
    async with sessionmaker() as session, session.begin():
        stored = await begin(session, request, clock=clock)
        if stored is not None:
            return stored
        runs.append(1)
        await asyncio.sleep(0.05)  # stay in the transaction while duplicates arrive
        if fail:
            raise _AbortError
        response = StoredResponse(status_code=201, body={"run": len(runs)})
        await complete(session, request, response)
        return response


def test_a_retry_gets_the_stored_response_and_the_work_runs_once(run_db: RunDb) -> None:
    request, clock = _request(), FrozenClock(START)
    runs: list[int] = []

    async def scenario(sessionmaker: Sessionmaker) -> list[StoredResponse]:
        return [await _attempt(sessionmaker, request, clock, runs) for _ in range(3)]

    assert run_db(scenario) == [StoredResponse(201, {"run": 1})] * 3
    assert len(runs) == 1


def test_concurrent_duplicates_run_the_work_exactly_once(run_db: RunDb) -> None:
    request, clock = _request(), FrozenClock(START)
    runs: list[int] = []

    async def scenario(sessionmaker: Sessionmaker) -> list[StoredResponse]:
        attempts = (_attempt(sessionmaker, request, clock, runs) for _ in range(8))
        return list(await asyncio.gather(*attempts))

    assert run_db(scenario) == [StoredResponse(201, {"run": 1})] * 8
    assert len(runs) == 1


def test_reusing_a_key_for_a_different_request_is_refused(run_db: RunDb) -> None:
    key, clock = uuid.uuid4().hex, FrozenClock(START)
    runs: list[int] = []

    async def scenario(sessionmaker: Sessionmaker) -> None:
        await _attempt(sessionmaker, _request(key=key, body=b'{"quoteId":"q1"}'), clock, runs)
        with pytest.raises(IdempotencyKeyReusedError):
            await _attempt(sessionmaker, _request(key=key, body=b'{"quoteId":"q2"}'), clock, runs)

    run_db(scenario)


def test_work_that_fails_releases_the_key(run_db: RunDb) -> None:
    request, clock = _request(), FrozenClock(START)
    runs: list[int] = []

    async def scenario(sessionmaker: Sessionmaker) -> StoredResponse:
        with contextlib.suppress(_AbortError):
            await _attempt(sessionmaker, request, clock, runs, fail=True)
        return await _attempt(sessionmaker, request, clock, runs)

    assert run_db(scenario) == StoredResponse(201, {"run": 2})


def test_keys_expire_after_24_hours_and_belong_to_their_sender(run_db: RunDb) -> None:
    key, clock = uuid.uuid4().hex, FrozenClock(START)
    runs: list[int] = []

    async def scenario(sessionmaker: Sessionmaker) -> list[StoredResponse]:
        first = await _attempt(sessionmaker, _request(key=key), clock, runs)
        other_user = await _attempt(sessionmaker, _request(key=key, scope="user:2"), clock, runs)
        clock.advance(timedelta(hours=24, seconds=1))
        after_expiry = await _attempt(sessionmaker, _request(key=key), clock, runs)
        return [first, other_user, after_expiry]

    assert run_db(scenario) == [
        StoredResponse(201, {"run": 1}),
        StoredResponse(201, {"run": 2}),
        StoredResponse(201, {"run": 3}),
    ]


def test_an_idempotent_route_replays_over_http(
    make_settings: SettingsFactory,
    request_app: Requester,
    database_url: str,
    csrf_headers: dict[str, str],
) -> None:
    app = create_app(make_settings(database_url=database_url))

    @app.post("/test/orders", status_code=201)
    async def create_order(request: Request, session: DbSession, clock: ClockDep) -> Response:
        idempotent = await idempotent_request(request, scope="user:http-test")
        async with session.begin():
            stored = await begin(session, idempotent, clock=clock)
            if stored is not None:
                return replay(stored)
            created = StoredResponse(201, {"orderId": str(new_public_id())})
            await complete(session, idempotent, created)
        return JSONResponse(created.body, status_code=created.status_code)

    headers = {**csrf_headers, "Idempotency-Key": f"order-{uuid.uuid4().hex}"}
    first = request_app(app, "POST", "/test/orders", headers=headers, json={"item": 1})
    retry = request_app(app, "POST", "/test/orders", headers=headers, json={"item": 1})
    changed = request_app(app, "POST", "/test/orders", headers=headers, json={"item": 2})

    assert first.status_code == retry.status_code == 201
    assert retry.json() == first.json()
    assert REPLAYED_HEADER.lower() not in first.headers
    assert retry.headers[REPLAYED_HEADER] == "true"
    assert (changed.status_code, changed.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")


@pytest.fixture
def with_redis(valkey_url: str) -> Callable[[Callable[[Redis], Awaitable[Any]]], Any]:
    def run(scenario: Callable[[Redis], Awaitable[Any]]) -> Any:
        async def wrapped() -> Any:
            redis = Redis.from_url(valkey_url)
            try:
                return await scenario(redis)
            finally:
                await redis.aclose()

        return asyncio.run(wrapped())

    return run


def test_the_sliding_window_counts_exactly(
    with_redis: Callable[[Callable[[Redis], Awaitable[Any]]], Any],
) -> None:
    clock = FrozenClock(START)
    rule = RateLimit(f"test.{uuid.uuid4().hex}", limit=3, window=timedelta(minutes=1))

    async def scenario(redis: Redis) -> list[tuple[bool, int, timedelta]]:
        limiter = RateLimiter(redis, clock, secret=b"test-only-secret")
        results = []
        for second in (0, 30, 45, 46, 61, 62):
            clock.set(START + timedelta(seconds=second))
            result = await limiter.hit(rule, "203.0.113.7")
            results.append((result.allowed, result.remaining, result.retry_after))
        return results

    assert with_redis(scenario) == [
        (True, 2, timedelta(0)),
        (True, 1, timedelta(0)),
        (True, 0, timedelta(0)),
        (False, 0, timedelta(seconds=14)),  # the hit at 0 s leaves the window at 60 s
        (True, 0, timedelta(0)),  # it has: room for one more
        (False, 0, timedelta(seconds=28)),  # next to leave is the hit at 30 s, at 90 s
    ]


def test_limits_are_per_subject_and_keys_hold_no_personal_data(
    with_redis: Callable[[Callable[[Redis], Awaitable[Any]]], Any],
) -> None:
    clock = FrozenClock(START)
    rule = RateLimit(f"test.{uuid.uuid4().hex}", limit=1, window=timedelta(minutes=1))

    async def scenario(redis: Redis) -> tuple[bool, bool, bool, list[bytes]]:
        limiter = RateLimiter(redis, clock, secret=b"test-only-secret")
        first = (await limiter.hit(rule, "+919876543210")).allowed
        again = (await limiter.hit(rule, "+919876543210")).allowed
        other = (await limiter.hit(rule, "+919999999999")).allowed
        keys = [key async for key in redis.scan_iter(match=f"ratelimit:{rule.name}:*")]
        return first, again, other, keys

    first, again, other, keys = with_redis(scenario)

    assert (first, again, other) == (True, False, True)
    assert len(keys) == 2
    assert not any(b"9876543210" in key or b"9999999999" in key for key in keys)


def test_a_rate_limited_route_answers_429_with_retry_after(
    make_settings: SettingsFactory, request_app: Requester, valkey_url: str
) -> None:
    app = create_app(make_settings(redis_url=valkey_url))
    rule = RateLimit(f"test.{uuid.uuid4().hex}", limit=2, window=timedelta(minutes=1))

    @app.get("/test/limited", dependencies=[Depends(rate_limited(rule))])
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    responses = [request_app(app, "GET", "/test/limited") for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[2].json()["code"] == "RATE_LIMITED"
    assert 1 <= int(responses[2].headers["retry-after"]) <= 60
