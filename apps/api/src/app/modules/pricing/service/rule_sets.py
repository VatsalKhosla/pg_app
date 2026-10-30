"""A PG's pricing rule sets (step 4.3, ADR 0038); each method is one transaction.

Ops start a draft, a copy of the set in force or empty for a PG's first, and change its rules.
Activating it checks the set against the PG's room categories and rent bands, then, in one step,
archives the set in force and puts the draft in its place. Active and archived sets never change
again (the database's triggers refuse it), so anything priced from one stays explained (rule 5).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from app.core import audit
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.outbox import enqueue
from app.modules.catalog.service import CatalogLookup, PricedCategory, PricedProperty
from app.modules.identity.service import Account, Accounts
from app.modules.pricing.domain.engine import PricingRule, RuleKind, RuleParams
from app.modules.pricing.domain.rule_sets import (
    MAX_RULES,
    CategoryBounds,
    RuleSetStatus,
    can_move,
    params_from_json,
    params_to_json,
    rule_set_problems,
)
from app.modules.pricing.errors import RuleSetInvalidError
from app.modules.pricing.models import PricingRuleRow, PricingRuleSet
from app.modules.pricing.repository import RentBandRepository, RuleSetRepository
from app.modules.pricing.service.policies import band_of

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock

NOTE_MAX_LENGTH: Final = 500


# A PG's rule set went into force: what its prices are has changed (ADR 0042).
RULES_CHANGED: Final = "pricing.rules_changed"


@dataclass(frozen=True, slots=True)
class RuleDraft:
    """A rule as ops write it: its label, kind and parameters, and the room categories it's for
    by their public ids (None for all of the PG's)."""

    label: str
    params: RuleParams
    room_categories: frozenset[uuid.UUID] | None
    enabled: bool


@dataclass(frozen=True, slots=True)
class _Columns:
    """A rule as its row keeps it."""

    kind: str
    label: str
    room_category_ids: list[int] | None
    params: dict[str, object]
    enabled: bool


@dataclass(frozen=True, slots=True)
class RuleView:
    row: PricingRuleRow
    params: RuleParams
    room_categories: tuple[PricedCategory, ...] | None


@dataclass(frozen=True, slots=True)
class RuleSetView:
    rule_set: PricingRuleSet
    property: PricedProperty
    rules: tuple[RuleView, ...]
    # What stops a draft going into force; empty for one that may, and for sets in force.
    problems: tuple[str, ...]
    activated_by: Account | None


@dataclass(frozen=True, slots=True)
class RuleSetSummary:
    rule_set: PricingRuleSet
    rules: int


def domain_rule(row: PricingRuleRow) -> PricingRule:
    """A stored rule as the engine takes it."""
    return PricingRule(
        label=row.label,
        params=params_from_json(RuleKind(row.kind), row.params),
        room_category_ids=None
        if row.room_category_ids is None
        else frozenset(row.room_category_ids),
        enabled=row.enabled,
    )


class RuleSetService:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._sets = RuleSetRepository(db)
        self._bands = RentBandRepository(db)
        self._catalog = CatalogLookup(db)
        self._accounts = Accounts(db)

    async def sets(self, property_id: uuid.UUID) -> tuple[PricedProperty, list[RuleSetSummary]]:
        async with self._db.begin():
            place = await self._place(property_id)
            sets = await self._sets.sets_of(place.id)
            counts = await self._sets.counts([found.id for found in sets])
            return place, [RuleSetSummary(found, counts.get(found.id, 0)) for found in sets]

    async def get(self, rule_set_id: uuid.UUID) -> RuleSetView:
        async with self._db.begin():
            found = await self._sets.get(rule_set_id)
            if found is None:
                raise NotFoundError
            return await self._view(found)

    async def start_draft(self, actor: Actor, property_id: uuid.UUID) -> RuleSetView:
        """The PG's draft: the one being edited, or a new one copied from the set in force."""
        async with self._db.begin():
            place = await self._place(property_id)
            await self._sets.lock_property(place.id)
            draft = await self._sets.in_status(place.id, RuleSetStatus.DRAFT)
            if draft is None:
                draft = PricingRuleSet(
                    property_id=place.id,
                    version=await self._sets.next_version(place.id),
                    status=RuleSetStatus.DRAFT,
                    created_by=actor.user_id,
                )
                self._sets.add(draft)
                await self._db.flush()
                active = await self._sets.in_status(place.id, RuleSetStatus.ACTIVE)
                for row in [] if active is None else await self._sets.rules_of(active.id):
                    self._sets.add(
                        PricingRuleRow(
                            rule_set_id=draft.id,
                            position=row.position,
                            kind=row.kind,
                            label=row.label,
                            room_category_ids=row.room_category_ids,
                            params=row.params,
                            enabled=row.enabled,
                        )
                    )
                await self._db.flush()
                await self._audit(actor, "pricing.rule_set_drafted", draft, version=draft.version)
            return await self._view(draft)

    async def add_rule(self, actor: Actor, rule_set_id: uuid.UUID, rule: RuleDraft) -> RuleSetView:
        async with self._db.begin():
            draft = await self._draft(rule_set_id)
            place = await self._place_of(draft)
            rows = await self._sets.rules_of(draft.id)
            if len(rows) >= MAX_RULES:
                raise RuleSetInvalidError([f"a set holds {MAX_RULES} rules at most"])
            columns = self._columns(rule, place)
            self._sets.add(
                PricingRuleRow(
                    rule_set_id=draft.id,
                    position=max((row.position for row in rows), default=-1) + 1,
                    kind=columns.kind,
                    label=columns.label,
                    room_category_ids=columns.room_category_ids,
                    params=columns.params,
                    enabled=columns.enabled,
                )
            )
            await self._db.flush()
            await self._audit(actor, "pricing.rule_added", draft, label=rule.label)
            return await self._view(draft)

    async def replace_rule(self, actor: Actor, rule_id: uuid.UUID, rule: RuleDraft) -> RuleSetView:
        async with self._db.begin():
            row, draft = await self._draft_rule(rule_id)
            columns = self._columns(rule, await self._place_of(draft))
            row.kind, row.label, row.enabled = columns.kind, columns.label, columns.enabled
            row.room_category_ids, row.params = columns.room_category_ids, columns.params
            await self._db.flush()
            await self._audit(actor, "pricing.rule_changed", draft, label=rule.label)
            return await self._view(draft)

    async def remove_rule(self, actor: Actor, rule_id: uuid.UUID) -> RuleSetView:
        async with self._db.begin():
            row, draft = await self._draft_rule(rule_id)
            label = row.label
            await self._sets.delete(row)
            await self._db.flush()
            await self._audit(actor, "pricing.rule_removed", draft, label=label)
            return await self._view(draft)

    async def activate(self, actor: Actor, rule_set_id: uuid.UUID, *, note: str) -> RuleSetView:
        """Put the draft in force, archiving the set before it: one step, or none."""
        async with self._db.begin():
            draft = await self._sets.get(rule_set_id, lock=True)
            if draft is None:
                raise NotFoundError
            await self._sets.lock_property(draft.property_id)
            if not can_move(RuleSetStatus(draft.status), RuleSetStatus.ACTIVE):
                raise InvalidTransitionError(f"An {draft.status} rule set can't be activated.")
            place = await self._place_of(draft)
            rows = await self._sets.rules_of(draft.id)
            if problems := await self._problems(place, rows):
                raise RuleSetInvalidError(problems)
            now = self._clock.now()
            active = await self._sets.in_status(place.id, RuleSetStatus.ACTIVE)
            if active is not None:
                active.status, active.archived_at = RuleSetStatus.ARCHIVED, now
                await self._db.flush()
            draft.status, draft.activated_at, draft.activated_by = (
                RuleSetStatus.ACTIVE,
                now,
                actor.user_id,
            )
            draft.note = note
            await self._db.flush()
            await self._audit(
                actor,
                "pricing.rule_set_activated",
                draft,
                version=draft.version,
                archived=None if active is None else active.version,
                rules=len(rows),
                note=note,
            )
            # Search's price summaries and the PG's cached pages follow (ADR 0042).
            await enqueue(
                self._db,
                RULES_CHANGED,
                {"property_id": place.id},
                clock=self._clock,
                dedupe_key=f"{RULES_CHANGED}:{draft.public_id}",
            )
            return await self._view(draft)

    async def discard(self, actor: Actor, rule_set_id: uuid.UUID) -> None:
        async with self._db.begin():
            draft = await self._draft(rule_set_id)
            await self._audit(actor, "pricing.rule_set_discarded", draft, version=draft.version)
            await self._sets.delete(draft)

    # Shared.

    async def _place(self, property_id: uuid.UUID) -> PricedProperty:
        place = await self._catalog.priced_property(property_id)
        if place is None:
            raise NotFoundError
        return place

    async def _place_of(self, rule_set: PricingRuleSet) -> PricedProperty:
        place = await self._catalog.priced_property_by_id(rule_set.property_id)
        assert place is not None  # noqa: S101 - a set's PG exists (foreign key)
        return place

    async def _draft(self, rule_set_id: uuid.UUID) -> PricingRuleSet:
        found = await self._sets.get(rule_set_id, lock=True)
        if found is None:
            raise NotFoundError
        if found.status != RuleSetStatus.DRAFT:
            raise InvalidTransitionError("Only a draft's rules change: start a draft.")
        return found

    async def _draft_rule(self, rule_id: uuid.UUID) -> tuple[PricingRuleRow, PricingRuleSet]:
        row = await self._sets.rule(rule_id, lock=True)
        if row is None:
            raise NotFoundError
        draft = await self._sets.set_of(row, lock=True)
        if draft.status != RuleSetStatus.DRAFT:
            raise InvalidTransitionError("Only a draft's rules change: start a draft.")
        return row, draft

    @staticmethod
    def _columns(rule: RuleDraft, place: PricedProperty) -> _Columns:
        """The rule's row, its room categories by internal id; 422 for one not the PG's."""
        ids = None
        if rule.room_categories is not None:
            by_public = {category.public_id: category.id for category in place.categories}
            if missing := [cid for cid in rule.room_categories if cid not in by_public]:
                raise RuleSetInvalidError(
                    [f"{len(missing)} of the room categories aren't this PG's"]
                )
            ids = sorted(by_public[cid] for cid in rule.room_categories)
        try:
            kind = PricingRule(rule.label, rule.params).kind
        except ValueError as error:
            raise RuleSetInvalidError([str(error)]) from error
        return _Columns(
            kind=kind,
            label=rule.label.strip(),
            room_category_ids=ids,
            params=dict(params_to_json(rule.params)),
            enabled=rule.enabled,
        )

    async def _problems(self, place: PricedProperty, rows: Sequence[PricingRuleRow]) -> list[str]:
        now = self._clock.now()
        bounds = []
        for category in place.categories:
            if not category.active:
                continue
            band = await self._bands.in_force(place.locality_id, category.occupancy, at=now)
            bounds.append(
                CategoryBounds(
                    category_id=category.id,
                    name=category.label,
                    base_rent_paise=category.base_rent,
                    owner_min_paise=category.owner_min,
                    owner_max_paise=category.owner_max,
                    band=None if band is None else band_of(band),
                )
            )
        known = {category.id for category in place.categories}
        return rule_set_problems(
            [domain_rule(row) for row in rows], bounds, known=known.__contains__
        )

    async def _view(self, rule_set: PricingRuleSet) -> RuleSetView:
        place = await self._place_of(rule_set)
        rows = await self._sets.rules_of(rule_set.id)
        by_id = {category.id: category for category in place.categories}
        rules = tuple(
            RuleView(
                row=row,
                params=params_from_json(RuleKind(row.kind), row.params),
                room_categories=None
                if row.room_category_ids is None
                else tuple(by_id[cid] for cid in row.room_category_ids if cid in by_id),
            )
            for row in rows
        )
        draft = rule_set.status == RuleSetStatus.DRAFT
        problems = tuple(await self._problems(place, rows)) if draft else ()
        people = await self._accounts.many(
            {rule_set.activated_by} if rule_set.activated_by is not None else set()
        )
        return RuleSetView(
            rule_set=rule_set,
            property=place,
            rules=rules,
            problems=problems,
            activated_by=people.get(rule_set.activated_by or 0),
        )

    async def _audit(
        self, actor: Actor, action: str, rule_set: PricingRuleSet, **details: object
    ) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.Actor("staff", actor.user_id),
            action=action,
            entity_type="pricing_rule_set",
            entity_id=str(rule_set.public_id),
            details=details,
        )
