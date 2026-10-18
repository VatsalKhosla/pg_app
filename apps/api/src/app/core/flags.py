"""Feature flags (ARCHITECTURE §22): declared and typed in code, stored in ``feature_flags``.

``FLAGS`` declares every flag with its type and default, the defaults that PRODUCT_CONTEXT §9
records. The database only overrides values; admins change them from step 4.1, with an audit
entry. Values are cached per process for at most 30 seconds. Reading a flag never fails: a stored
value of the wrong type, or a database that can't be reached, falls back to the last good value
or the default, and logs an error.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, cast

import structlog
from fastapi import Request  # noqa: TC002 - FastAPI reads dependency signatures at runtime
from sqlalchemy import BigInteger, Text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.clock import Clock

type FlagValue = bool | str

CACHE_TTL: Final = timedelta(seconds=30)

logger = structlog.stdlib.get_logger(__name__)


class Flag(StrEnum):
    REMOTE_BOOKING_ENABLED = "remote_booking_enabled"
    TOKEN_MODE = "token_mode"  # noqa: S105 - a flag name, not a password
    RENT_VIA_APP_ENABLED = "rent_via_app_enabled"
    HIDE_OWNER_CONTACT = "hide_owner_contact"
    INSTANT_CONFIRM_DEFAULT = "instant_confirm_default"
    REVIEWS_ENABLED = "reviews_enabled"
    WHATSAPP_ENABLED = "whatsapp_enabled"
    PRICE_SUGGESTIONS_ENABLED = "price_suggestions_enabled"


@dataclass(frozen=True, slots=True)
class FlagSpec:
    default: FlagValue
    description: str
    choices: frozenset[str] = frozenset()

    def accepts(self, value: object) -> bool:
        if isinstance(self.default, bool):
            return isinstance(value, bool)
        return isinstance(value, str) and value in self.choices


FLAGS: Final[Mapping[Flag, FlagSpec]] = MappingProxyType(
    {
        Flag.REMOTE_BOOKING_ENABLED: FlagSpec(
            False, "Students can reserve a bed without a visit first (season one is visit-first)."
        ),
        Flag.TOKEN_MODE: FlagSpec(
            "payment",
            "How the token is taken: a normal payment held until move-in, or a UPI one-time"
            " mandate (only once Razorpay enables mandates for the account).",
            frozenset({"payment", "upi_mandate"}),
        ),
        Flag.RENT_VIA_APP_ENABLED: FlagSpec(
            False, "The rest of the first month's rent can be paid through the app (Phase 9)."
        ),
        Flag.HIDE_OWNER_CONTACT: FlagSpec(
            True,
            "Owner phone and exact address stay hidden until a visit is scheduled or a booking"
            " is confirmed (pending legal advice).",
        ),
        Flag.INSTANT_CONFIRM_DEFAULT: FlagSpec(
            False, "New properties confirm bookings instantly instead of waiting for the owner."
        ),
        Flag.REVIEWS_ENABLED: FlagSpec(False, "Verified-resident reviews (Phase 9)."),
        Flag.WHATSAPP_ENABLED: FlagSpec(False, "Notifications on WhatsApp (Phase 9)."),
        Flag.PRICE_SUGGESTIONS_ENABLED: FlagSpec(
            False, "Price suggestions for owners from demand data (Phase 9)."
        ),
    }
)


class FeatureFlag(Model):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(Text, unique=True)
    value: Mapped[Any] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)  # references users from step 1.1


class FeatureFlags:
    """Flag values for one process: loaded from the database, cached for ``ttl``."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        clock: Clock,
        *,
        ttl: timedelta = CACHE_TTL,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._clock = clock
        self._ttl = ttl
        self._stored: Mapping[str, object] = {}
        self._fresh_until: datetime | None = None
        self._lock = asyncio.Lock()

    async def is_enabled(self, flag: Flag) -> bool:
        value = await self.value(flag)
        if not isinstance(value, bool):
            msg = f"{flag} is not an on/off flag"
            raise TypeError(msg)
        return value

    async def choice(self, flag: Flag) -> str:
        value = await self.value(flag)
        if not isinstance(value, str):
            msg = f"{flag} is an on/off flag, not a choice"
            raise TypeError(msg)
        return value

    async def value(self, flag: Flag) -> FlagValue:
        spec = FLAGS[flag]
        stored = (await self._current()).get(flag.value, spec.default)
        if spec.accepts(stored):
            return cast("FlagValue", stored)
        logger.error("invalid feature flag value in the database; using the default", flag=flag)
        return spec.default

    async def _current(self) -> Mapping[str, object]:
        if self._is_fresh():
            return self._stored
        async with self._lock:
            if self._is_fresh():  # another caller refreshed while this one waited
                return self._stored
            try:
                async with self._sessionmaker() as session:
                    rows = await session.execute(select(FeatureFlag.key, FeatureFlag.value))
                    self._stored = {row.key: row.value for row in rows.all()}
            except SQLAlchemyError, OSError:
                logger.exception("could not load feature flags; using the last known values")
            # Also after a failure, so an unreachable database is retried every ttl, not per call.
            self._fresh_until = self._clock.now() + self._ttl
            return self._stored

    def _is_fresh(self) -> bool:
        return self._fresh_until is not None and self._clock.now() < self._fresh_until


def get_flags(request: Request) -> FeatureFlags:
    flags: FeatureFlags = request.app.state.flags
    return flags
