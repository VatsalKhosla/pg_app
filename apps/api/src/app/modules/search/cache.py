"""The map pins' cache in Redis (step 3.3, ADR 0029): each answer kept for a minute with its ETag.
Only a convenience: when Redis is down, pins come straight from the database."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from redis.exceptions import RedisError

from app.modules.search.domain.pins import PINS_TTL_SECONDS

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Cached:
    etag: str
    body: bytes


class PinCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> Cached | None:
        try:
            stored = await self._redis.get(key)
        except RedisError, OSError, TimeoutError:
            logger.warning("map pins cache unavailable")
            return None
        if not isinstance(stored, bytes) or b"\n" not in stored:
            return None
        etag, body = stored.split(b"\n", 1)
        return Cached(etag=etag.decode(), body=body)

    async def put(self, key: str, cached: Cached) -> None:
        try:
            await self._redis.set(
                key, cached.etag.encode() + b"\n" + cached.body, ex=PINS_TTL_SECONDS
            )
        except RedisError, OSError, TimeoutError:
            logger.warning("map pins cache unavailable")
