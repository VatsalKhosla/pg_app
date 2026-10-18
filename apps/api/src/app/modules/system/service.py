"""Readiness checks: can this instance reach the database and Redis right now?"""

import asyncio
from typing import TYPE_CHECKING

import structlog
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.modules.system.domain.readiness import CheckState, overall_state
from app.modules.system.schemas import Readiness

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine

CHECK_TIMEOUT_SECONDS = 2.0

logger = structlog.stdlib.get_logger(__name__)


class ReadinessService:
    def __init__(self, *, engine: AsyncEngine, redis: Redis) -> None:
        self._engine = engine
        self._redis = redis

    async def check(self) -> Readiness:
        async with asyncio.TaskGroup() as group:
            database = group.create_task(self._check_database())
            redis = group.create_task(self._check_redis())
        checks = {"database": database.result(), "redis": redis.result()}
        return Readiness(status=overall_state(checks), checks=checks)

    async def _check_database(self) -> CheckState:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SECONDS), self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError, OSError, TimeoutError:
            logger.warning("readiness check failed", check="database", exc_info=True)
            return "unavailable"
        return "ok"

    async def _check_redis(self) -> CheckState:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
                await self._redis.ping()
        except RedisError, OSError, TimeoutError:
            logger.warning("readiness check failed", check="redis", exc_info=True)
            return "unavailable"
        return "ok"
