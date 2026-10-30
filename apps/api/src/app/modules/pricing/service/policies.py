"""Pricing's use cases (step 4.1, ADR 0036); each method is one transaction.

The policies in force, for quotes and the public pages, and admins' changes to them. A change
ends the version in force and starts the next from that moment, so nothing already priced moves
(rule 5). Each change is audited with what it was and what it became, and tells the web app its
policy pages are out of date.
"""

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any, Final

from app.core import audit
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.money import BasisPoints, Paise
from app.core.outbox import enqueue
from app.core.web_cache import POLICIES_TAG, ask_to_revalidate
from app.modules.geo.service import GeoLookup, LocalityRef
from app.modules.identity.service import Account, Accounts
from app.modules.pricing.domain.policies import (
    BandSource,
    BookingPolicy,
    FeeBasis,
    FeePolicy,
    GstMode,
    LateCancelPolicy,
    PolicyKind,
    PricingCaps,
    RentBand,
    band_problems,
    booking_problems,
    caps_problems,
    fee_problems,
)
from app.modules.pricing.errors import PolicyInvalidError, PricingConfigError
from app.modules.pricing.models import (
    BookingPolicyVersion,
    FeePolicyVersion,
    PolicyVersion,
    PricingCapsVersion,
)
from app.modules.pricing.models import RentBand as RentBandRow
from app.modules.pricing.repository import PolicyRepository, RentBandRepository

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.catalog.domain.rooms import Occupancy

HISTORY_LIMIT: Final = 20
BANDS_LIMIT: Final = 200

# A band began or ended for a locality and sharing, or the caps changed: prices may move
# (ADR 0042).
BAND_CHANGED: Final = "pricing.band_changed"
CAPS_CHANGED: Final = "pricing.caps_changed"

_MODELS: Final[dict[PolicyKind, type[PolicyVersion]]] = {
    PolicyKind.FEE: FeePolicyVersion,
    PolicyKind.BOOKING: BookingPolicyVersion,
    PolicyKind.CAPS: PricingCapsVersion,
}


@dataclass(frozen=True, slots=True)
class Policies:
    """The policies in force."""

    fee: FeePolicy
    booking: BookingPolicy
    caps: PricingCaps


@dataclass(frozen=True, slots=True)
class VersionView[V: PolicyVersion]:
    version: V
    # The admin who made it; None for the seeded defaults, or once their account has gone.
    changed_by: Account | None


@dataclass(frozen=True, slots=True)
class BandView:
    band: RentBandRow
    locality: LocalityRef
    changed_by: Account | None


def fee_policy(row: FeePolicyVersion) -> FeePolicy:
    return FeePolicy(
        rate_bps=BasisPoints(row.rate_bps),
        basis=FeeBasis(row.basis),
        gst_rate_bps=BasisPoints(row.gst_rate_bps),
        gst_mode=GstMode(row.gst_mode),
    )


def booking_policy(row: BookingPolicyVersion) -> BookingPolicy:
    return BookingPolicy(
        token_paise=Paise(row.token_paise),
        hold_minutes=row.hold_minutes,
        free_cancel_days=row.free_cancel_days,
        check_window_hours=row.check_window_hours,
        confirm_deadline_hours=row.confirm_deadline_hours,
        no_show_days=row.no_show_days,
        late_cancel_policy=LateCancelPolicy(row.late_cancel_policy),
        max_active_holds_per_user=row.max_active_holds_per_user,
        max_advance_days=row.max_advance_days,
    )


def pricing_caps(row: PricingCapsVersion) -> PricingCaps:
    return PricingCaps(
        max_premium_bps=BasisPoints(row.max_premium_bps),
        max_discount_bps=BasisPoints(row.max_discount_bps),
        rounding_step_paise=Paise(row.rounding_step_paise),
    )


def band_of(row: RentBandRow) -> RentBand:
    return RentBand(
        min_rent_paise=Paise(row.min_rent_paise),
        max_rent_paise=Paise(row.max_rent_paise),
        source=BandSource(row.source),
        reference=row.reference,
    )


def _values(policy: FeePolicy | BookingPolicy | PricingCaps) -> dict[str, Any]:
    """A policy's fields as its table's columns hold them."""
    return {field.name: getattr(policy, field.name) for field in fields(policy)}


def _plain(values: dict[str, Any]) -> dict[str, object]:
    """Values as the audit log's JSON holds them."""
    return {name: str(value) if isinstance(value, str) else value for name, value in values.items()}


class BookingTerms:
    """The booking terms a quote was made under: a booking keeps them for good, so a later
    change to the terms never alters a booking already made (ADR 0046). In the caller's
    transaction."""

    def __init__(self, db: AsyncSession) -> None:
        self._policies = PolicyRepository(db)

    async def of(self, booking_policy_id: int) -> BookingPolicy:
        return booking_policy(await self._policies.version(BookingPolicyVersion, booking_policy_id))


class PolicyService:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._policies = PolicyRepository(db)
        self._accounts = Accounts(db)

    async def current(self) -> Policies:
        """The policies in force now."""
        now = self._clock.now()
        async with self._db.begin():
            fee = await self._policies.in_force(FeePolicyVersion, at=now)
            booking = await self._policies.in_force(BookingPolicyVersion, at=now)
            caps = await self._policies.in_force(PricingCapsVersion, at=now)
        if fee is None or booking is None or caps is None:
            raise PricingConfigError
        return Policies(
            fee=fee_policy(fee), booking=booking_policy(booking), caps=pricing_caps(caps)
        )

    async def in_force(self) -> dict[PolicyKind, VersionView[PolicyVersion]]:
        """Each policy's version in force, with who made it: what admins see."""
        now = self._clock.now()
        async with self._db.begin():
            found = {
                kind: await self._policies.in_force(model, at=now)
                for kind, model in _MODELS.items()
            }
            versions = {kind: version for kind, version in found.items() if version is not None}
            if len(versions) != len(_MODELS):
                raise PricingConfigError
            return await self._views(versions)

    async def history(self) -> dict[PolicyKind, list[VersionView[PolicyVersion]]]:
        """Each policy's latest versions, newest first."""
        async with self._db.begin():
            found = {
                kind: await self._policies.history(model, limit=HISTORY_LIMIT)
                for kind, model in _MODELS.items()
            }
            people = await self._people(
                version.changed_by for versions in found.values() for version in versions
            )
            return {
                kind: [
                    VersionView(version, people.get(version.changed_by or 0))
                    for version in versions
                ]
                for kind, versions in found.items()
            }

    async def change_fee(
        self, actor: Actor, policy: FeePolicy, *, note: str
    ) -> VersionView[PolicyVersion]:
        return await self._change(
            actor, PolicyKind.FEE, _values(policy), fee_problems(policy), note=note
        )

    async def change_booking(
        self, actor: Actor, policy: BookingPolicy, *, note: str
    ) -> VersionView[PolicyVersion]:
        return await self._change(
            actor, PolicyKind.BOOKING, _values(policy), booking_problems(policy), note=note
        )

    async def change_caps(
        self, actor: Actor, caps: PricingCaps, *, note: str
    ) -> VersionView[PolicyVersion]:
        return await self._change(
            actor, PolicyKind.CAPS, _values(caps), caps_problems(caps), note=note
        )

    async def _change(
        self,
        actor: Actor,
        kind: PolicyKind,
        values: dict[str, Any],
        problems: list[str],
        *,
        note: str,
    ) -> VersionView[PolicyVersion]:
        if problems:
            raise PolicyInvalidError(problems)
        model = _MODELS[kind]
        async with self._db.begin():
            # One change at a time: the next waits, then sees this one in force.
            await self._policies.lock(model.__tablename__)
            now = self._clock.now()
            current = await self._policies.in_force(model, at=now)
            before = None if current is None else {name: getattr(current, name) for name in values}
            if before == values:
                raise PolicyInvalidError(["that's the policy in force already"])
            if current is not None:
                if current.effective_from >= now:
                    raise InvalidTransitionError("That policy changed a moment ago: reload it.")
                current.effective_to = now
                await self._db.flush()
            version = model(effective_from=now, changed_by=actor.user_id, note=note, **values)
            self._policies.add(version)
            await self._db.flush()
            await audit.record(
                self._db,
                clock=self._clock,
                actor=audit.Actor("staff", actor.user_id),
                action=f"pricing.{kind}_policy_changed",
                entity_type=f"{kind}_policy",
                entity_id=str(version.public_id),
                details={
                    "before": None if before is None else _plain(before),
                    "after": _plain(values),
                    "note": note,
                },
            )
            # The pages that state the policies (Pricing, the token, refunds) say the new ones.
            await ask_to_revalidate(self._db, self._clock, [POLICIES_TAG])
            if kind == PolicyKind.CAPS:
                # Every dynamic price may move: search's summaries follow (ADR 0042).
                await enqueue(
                    self._db,
                    CAPS_CHANGED,
                    {"version": str(version.public_id)},
                    clock=self._clock,
                    dedupe_key=f"{CAPS_CHANGED}:{version.public_id}",
                )
            return (await self._views({kind: version}))[kind]

    async def _views[V: PolicyVersion](
        self, versions: dict[PolicyKind, V]
    ) -> dict[PolicyKind, VersionView[V]]:
        people = await self._people(version.changed_by for version in versions.values())
        return {
            kind: VersionView(version, people.get(version.changed_by or 0))
            for kind, version in versions.items()
        }

    async def _people(self, user_ids: Iterable[int | None]) -> dict[int, Account]:
        return await self._accounts.many({user_id for user_id in user_ids if user_id is not None})


class RentBandService:
    """Rent bands (rule 6): the rents a locality allows for one occupancy. Setting one ends the
    band in force for that locality and occupancy, if any."""

    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._bands = RentBandRepository(db)
        self._policies = PolicyRepository(db)
        self._geo = GeoLookup(db)
        self._accounts = Accounts(db)

    async def listed(self, *, locality: str | None, ended: bool) -> list[BandView]:
        async with self._db.begin():
            locality_id = None
            if locality is not None:
                found = await self._geo.locality(locality)
                if found is None:
                    return []
                locality_id = found.id
            bands = await self._bands.listed(
                locality_id=locality_id, at=self._clock.now(), ended=ended, limit=BANDS_LIMIT
            )
            return await self._views(bands)

    async def set(
        self, actor: Actor, *, locality: str, occupancy: Occupancy, band: RentBand, note: str
    ) -> BandView:
        problems = band_problems(band)
        async with self._db.begin():
            place = await self._geo.locality(locality)
            if place is None:
                problems = ["no locality has that slug", *problems]
            if problems or place is None:
                raise PolicyInvalidError(problems)
            await self._policies.lock(RentBandRow.__tablename__)
            now = self._clock.now()
            current = await self._bands.in_force(place.id, occupancy, at=now)
            if current is not None:
                if current.effective_from >= now:
                    raise InvalidTransitionError("That band changed a moment ago: reload it.")
                current.effective_to = now
                await self._db.flush()
            row = RentBandRow(
                locality_id=place.id,
                occupancy=occupancy,
                min_rent_paise=band.min_rent_paise,
                max_rent_paise=band.max_rent_paise,
                source=band.source,
                reference=band.reference.strip(),
                effective_from=now,
                changed_by=actor.user_id,
                note=note,
            )
            self._db.add(row)
            await self._db.flush()
            await self._changed(place.id, row, "set")
            await self._audit(
                actor,
                "pricing.rent_band_set",
                row,
                ended=None if current is None else str(current.public_id),
                locality=locality,
                occupancy=str(occupancy),
                min_rent_paise=band.min_rent_paise,
                max_rent_paise=band.max_rent_paise,
                source=str(band.source),
                note=note,
            )
            return (await self._views([row]))[0]

    async def end(self, actor: Actor, band_id: uuid.UUID, *, note: str) -> BandView:
        async with self._db.begin():
            await self._policies.lock(RentBandRow.__tablename__)
            band = await self._bands.get(band_id, lock=True)
            if band is None:
                raise NotFoundError
            now = self._clock.now()
            if band.effective_to is not None or band.effective_from >= now:
                raise InvalidTransitionError("Only a band in force can be ended.")
            band.effective_to = now
            await self._changed(band.locality_id, band, "ended")
            await self._audit(actor, "pricing.rent_band_ended", band, note=note)
            return (await self._views([band]))[0]

    async def _changed(self, locality_id: int, band: RentBandRow, change: str) -> None:
        """The locality's PGs' prices may move: search's summaries and their pages follow."""
        await enqueue(
            self._db,
            BAND_CHANGED,
            {"locality_id": locality_id, "band": str(band.public_id), "change": change},
            clock=self._clock,
            dedupe_key=f"{BAND_CHANGED}:{band.public_id}:{change}",
        )

    async def _audit(self, actor: Actor, action: str, band: RentBandRow, **details: object) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.Actor("staff", actor.user_id),
            action=action,
            entity_type="rent_band",
            entity_id=str(band.public_id),
            details=details,
        )

    async def _views(self, bands: list[RentBandRow]) -> list[BandView]:
        """Bands with their localities and who set them: two queries, however many."""
        places = await self._geo.localities({band.locality_id for band in bands})
        people = await self._accounts.many(
            {band.changed_by for band in bands if band.changed_by is not None}
        )
        return [
            BandView(band, places[band.locality_id], people.get(band.changed_by or 0))
            for band in bands
        ]
