"""Pricing's integrity alerts (ARCHITECTURE §8.7; step 4.8, ADR 0043).

The checks run in the caller's transaction: the market and clamp checks in the nightly job's,
the churn check in the activation of a rule set. Each raises an alert once for what it's about
(its key), however often it runs. Ops read and resolve them, one transaction a method.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Final

from app.core import audit
from app.core.calendar import INDIA, india_date
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.pagination import split_page
from app.modules.catalog.service import CatalogLookup
from app.modules.geo.service import GeoLookup
from app.modules.identity.service import Account, Accounts
from app.modules.pricing.domain.alerts import (
    AlertKind,
    alert_key,
    below_market,
    churning,
    clamps_frequent,
    week_of,
)
from app.modules.pricing.domain.quotes import median_rent
from app.modules.pricing.repository import AlertRepository, RuleSetRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.money import Paise
    from app.core.pagination import PageRequest
    from app.modules.catalog.domain.rooms import Occupancy
    from app.modules.catalog.service import PricedProperty
    from app.modules.pricing.models import PricingAlert

# What the market check says when it resolves an alert itself.
NO_LONGER_BELOW: Final = (
    "The rent is no longer more than 25% below its market, or the room is no longer listed."
)


def _place(public_id: uuid.UUID, name: str) -> dict[str, str]:
    return {"id": str(public_id), "name": name}


class AlertChecks:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._clock = clock
        self._alerts = AlertRepository(db)
        self._sets = RuleSetRepository(db)
        self._catalog = CatalogLookup(db)
        self._geo = GeoLookup(db)

    async def market(self) -> int:
        """Each published room whose listed rent is more than 25% below the median for its
        sharing in its locality's other published PGs, raised once at that rent; open ones
        that no longer are, resolved. How many it raised."""
        now = self._clock.now()
        rooms = await self._catalog.listed_rooms()
        markets: dict[tuple[int, Occupancy], list[tuple[int, Paise]]] = defaultdict(list)
        for room in rooms:
            markets[room.locality_id, room.occupancy].append((room.property_id, room.base_rent))
        localities = await self._geo.localities({room.locality_id for room in rooms})
        below, raised = set[str](), 0
        for room in rooms:
            others = [
                rent
                for owner, rent in markets[room.locality_id, room.occupancy]
                if owner != room.property_id
            ]
            median = median_rent(others)
            if median is None or not below_market(room.base_rent, median, len(others)):
                continue
            key = alert_key(AlertKind.RENT_BELOW_MARKET, room.category_public_id, room.base_rent)
            below.add(key)
            raised += await self._alerts.raise_once(
                kind=AlertKind.RENT_BELOW_MARKET,
                key=key,
                property_id=room.property_id,
                room_category_id=room.category_id,
                details={
                    "property": _place(room.property_public_id, room.property_name),
                    "room": {"id": str(room.category_public_id), "label": room.label},
                    "listed_rent_paise": room.base_rent,
                    "median_rent_paise": median,
                    "comparables": len(others),
                    "locality": localities[room.locality_id].name,
                },
                raised_at=now,
            )
        for alert in await self._alerts.open_of_kind(AlertKind.RENT_BELOW_MARKET):
            if alert.key not in below:
                alert.resolved_at, alert.resolution = now, NO_LONGER_BELOW
        return raised

    async def clamps(self) -> int:
        """Last week's PGs (Monday to Sunday in India) whose quotes a limit held back more than
        a fifth of the time, raised once for that week. How many it raised."""
        now = self._clock.now()
        week = week_of(india_date(now)) - timedelta(weeks=1)
        raised = 0
        for property_id, quotes, clamped in await self._alerts.weekly_quotes(
            week, week + timedelta(days=6)
        ):
            if not clamps_frequent(quotes, clamped):
                continue
            place = await self._catalog.priced_property_by_id(property_id)
            assert place is not None  # noqa: S101 - a quote's PG exists (foreign key)
            raised += await self._alerts.raise_once(
                kind=AlertKind.CLAMPS_FREQUENT,
                key=alert_key(AlertKind.CLAMPS_FREQUENT, place.public_id, week),
                property_id=property_id,
                room_category_id=None,
                details={
                    "property": _place(place.public_id, place.name),
                    "week": week.isoformat(),
                    "quotes": quotes,
                    "clamped": clamped,
                },
                raised_at=now,
            )
        return raised

    async def churn(self, place: PricedProperty) -> bool:
        """After one of the PG's rule sets went into force: this week's activations, if they're
        too many, raised once for the week. Whether it raised one."""
        now = self._clock.now()
        week = week_of(india_date(now))
        activations = await self._sets.activations_since(
            place.id, datetime.combine(week, time(), tzinfo=INDIA)
        )
        if not churning(activations):
            return False
        return await self._alerts.raise_once(
            kind=AlertKind.RULE_CHURN,
            key=alert_key(AlertKind.RULE_CHURN, place.public_id, week),
            property_id=place.id,
            room_category_id=None,
            details={
                "property": _place(place.public_id, place.name),
                "week": week.isoformat(),
                "activations": activations,
            },
            raised_at=now,
        )


@dataclass(frozen=True, slots=True)
class AlertView:
    row: PricingAlert
    # Who resolved it; None while it's open, when the check did, or once their account has gone.
    resolved_by: Account | None


class AlertService:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._alerts = AlertRepository(db)
        self._accounts = Accounts(db)

    async def page(
        self, page: PageRequest, *, resolved: bool
    ) -> tuple[list[AlertView], uuid.UUID | None]:
        """Open or resolved alerts, newest first."""
        async with self._db.begin():
            rows = await self._alerts.page(resolved=resolved, before=page.after, limit=page.limit)
            items, next_cursor = split_page(rows, page, cursor_of=lambda row: row.public_id)
            return await self._views(items), next_cursor

    async def resolve(self, actor: Actor, alert_id: uuid.UUID, *, note: str) -> AlertView:
        """Ops have looked at it: resolved, with what they found. Audited."""
        async with self._db.begin():
            alert = await self._alerts.get(alert_id, lock=True)
            if alert is None:
                raise NotFoundError
            if alert.resolved_at is not None:
                raise InvalidTransitionError("That alert is resolved already.")
            alert.resolved_at, alert.resolved_by, alert.resolution = (
                self._clock.now(),
                actor.user_id,
                note,
            )
            await audit.record(
                self._db,
                clock=self._clock,
                actor=audit.Actor("staff", actor.user_id),
                action="pricing.alert_resolved",
                entity_type="pricing_alert",
                entity_id=str(alert.public_id),
                details={"kind": alert.kind, "note": note},
            )
            return (await self._views([alert]))[0]

    async def _views(self, rows: list[PricingAlert]) -> list[AlertView]:
        people = await self._accounts.many(
            {row.resolved_by for row in rows if row.resolved_by is not None}
        )
        return [
            AlertView(row, None if row.resolved_by is None else people.get(row.resolved_by))
            for row in rows
        ]
