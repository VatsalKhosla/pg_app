"""Sliding-window rate limits in Redis (ARCHITECTURE §17): per IP, per user, per phone, per route.

Each limit keeps a sorted set of recent hits. One Lua script drops hits older than the window,
counts the rest and records the new hit atomically. It uses the injectable clock's time, not
Redis's, so tests can move time. Subjects (IP addresses, phone numbers) are stored only as keyed
digests. When Redis can't be reached, a limit fails open (public reads) or closed (abuse-prone
actions such as sending OTPs), by its own setting.
"""

import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

import structlog
from fastapi import Request  # noqa: TC002 - FastAPI reads dependency signatures at runtime
from redis.exceptions import RedisError

from app.core.errors import AppError, ServiceUnavailableError
from app.core.hashing import keyed_digest

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from redis.asyncio import Redis

    from app.core.clock import Clock

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_MILLISECOND: Final = timedelta(milliseconds=1)

# KEYS[1]: the limit's sorted set. ARGV: now (ms), window (ms), limit, a unique member.
# Returns {allowed (1 or 0), remaining, retry_after_ms}.
_SLIDING_WINDOW: Final = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count < limit then
  redis.call('ZADD', key, now, ARGV[4])
  redis.call('PEXPIRE', key, window)
  return {1, limit - count - 1, 0}
end
local oldest = tonumber(redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')[2])
return {0, 0, oldest + window - now}
"""

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimit:
    name: str
    limit: int
    window: timedelta
    fail_open: bool = True  # when Redis is down: let requests through (True) or refuse them

    def __post_init__(self) -> None:
        if self.limit < 1 or self.window < _MILLISECOND:
            msg = "a rate limit needs limit >= 1 and a window of at least a millisecond"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: timedelta


class RateLimitedError(AppError):
    status = 429
    code = "RATE_LIMITED"
    title = "Too many requests"

    def __init__(self, retry_after: timedelta) -> None:
        seconds = max(1, math.ceil(retry_after / timedelta(seconds=1)))
        super().__init__(f"Try again in {seconds} seconds.", headers={"Retry-After": str(seconds)})


class RateLimiter:
    def __init__(self, redis: Redis, clock: Clock, *, secret: bytes) -> None:
        self._clock = clock
        self._secret = secret
        self._script = redis.register_script(_SLIDING_WINDOW)

    async def hit(self, rule: RateLimit, subject: str) -> RateLimitResult:
        """Count one hit for ``subject`` against ``rule`` and say whether it is allowed."""
        now_ms = (self._clock.now() - _EPOCH) // _MILLISECOND
        digest = keyed_digest(self._secret, purpose=f"ratelimit:{rule.name}", value=subject)
        allowed, remaining, retry_after_ms = await self._script(
            keys=[f"ratelimit:{rule.name}:{digest}"],
            args=[
                now_ms,
                rule.window // _MILLISECOND,
                rule.limit,
                f"{now_ms}:{secrets.token_hex(8)}",
            ],
        )
        return RateLimitResult(
            allowed=allowed == 1,
            remaining=int(remaining),
            retry_after=timedelta(milliseconds=int(retry_after_ms)),
        )


def client_ip(request: Request) -> str:
    """The client's address. Behind the load balancer, uvicorn's --proxy-headers (limited to the
    balancer's addresses with --forwarded-allow-ips) makes this the real client (Phase 8)."""
    return request.client.host if request.client is not None else "unknown"


async def enforce(limiter: RateLimiter, rule: RateLimit, subject: str) -> None:
    """Count a hit for ``subject``; raise RateLimitedError (429) once over the limit. If Redis is
    down, let the request through or refuse it with 503, as the rule says."""
    try:
        result = await limiter.hit(rule, subject)
    except RedisError, OSError, TimeoutError:
        logger.exception("rate limiter unavailable", limit=rule.name, fail_open=rule.fail_open)
        if rule.fail_open:
            return
        raise ServiceUnavailableError("Please try again in a moment.") from None
    if not result.allowed:
        logger.info("rate limit exceeded", limit=rule.name)
        raise RateLimitedError(result.retry_after)


def rate_limited(
    rule: RateLimit, *, subject: Callable[[Request], str] = client_ip
) -> Callable[[Request], Awaitable[None]]:
    """A FastAPI dependency that enforces ``rule`` per ``subject`` (the client IP by default)."""

    async def check(request: Request) -> None:
        limiter: RateLimiter = request.app.state.rate_limiter
        await enforce(limiter, rule, subject(request))

    return check
