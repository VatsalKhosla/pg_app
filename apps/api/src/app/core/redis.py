"""The Redis client (cache and rate limits; Valkey locally). Nothing durable lives only in Redis."""

from typing import TYPE_CHECKING

from redis.asyncio import Redis

if TYPE_CHECKING:
    from app.config import Settings


def create_redis(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
