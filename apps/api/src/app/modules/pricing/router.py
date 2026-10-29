"""Pricing routes (ARCHITECTURE §15): the policies in force, for anyone, and admins' changes to
them and to rent bands (step 4.1, ADR 0036)."""

import uuid
from datetime import datetime
from typing import Annotated, Final, TypedDict

from fastapi import APIRouter, Query, Response, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.money import BasisPoints, Paise
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.identity.service import Account
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
)
from app.modules.pricing.models import (
    BookingPolicyVersion,
    FeePolicyVersion,
    PolicyVersion,
    PricingCapsVersion,
)
from app.modules.pricing.policies import can_manage_pricing_policies
from app.modules.pricing.schemas import (
    AdminPolicies,
    BandLocality,
    BookingPolicyInput,
    BookingPolicyVersionInfo,
    BookingTerms,
    Changer,
    FeePolicyInput,
    FeePolicyVersionInfo,
    PlacementFeeTerms,
    PolicyHistory,
    PricingCapsInput,
    PricingCapsVersionInfo,
    PublicPolicies,
    RentBandEnd,
    RentBandInfo,
    RentBandInput,
    RentBandList,
)
from app.modules.pricing.service import BandView, PolicyService, RentBandService, VersionView

router = APIRouter(prefix="/v1", tags=["pricing"])

# They change rarely, and the web app's pages for them are revalidated when they do.
CACHE_CONTROL: Final = "public, max-age=300"

LocalityFilter = Annotated[str | None, Query(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)]


def _admin(actor: CurrentActor) -> None:
    if not can_manage_pricing_policies(actor):
        raise ForbiddenError


@router.get("/policies", summary="The fee and booking terms in force")
async def policies(response: Response, db: DbSession, clock: ClockDep) -> PublicPolicies:
    """What owners pay and what students can rely on: the placement fee, the token, holds,
    cancellation and the check window. Public."""
    response.headers["Cache-Control"] = CACHE_CONTROL
    current = await PolicyService(db, clock).current()
    fee, booking = current.fee, current.booking
    return PublicPolicies(
        placement_fee=PlacementFeeTerms(
            rate_bps=fee.rate_bps,
            basis=fee.basis,
            gst_rate_bps=fee.gst_rate_bps,
            gst_mode=fee.gst_mode,
        ),
        booking=BookingTerms(
            token_paise=booking.token_paise,
            hold_minutes=booking.hold_minutes,
            free_cancel_days=booking.free_cancel_days,
            check_window_hours=booking.check_window_hours,
            confirm_deadline_hours=booking.confirm_deadline_hours,
            late_cancel_policy=booking.late_cancel_policy,
        ),
    )


def _changer(account: Account | None) -> Changer | None:
    return None if account is None else Changer(id=account.public_id, name=account.name)


class _Meta(TypedDict):
    id: uuid.UUID
    effective_from: datetime
    effective_to: datetime | None
    changed_by: Changer | None
    note: str


def _meta(version: PolicyVersion, account: Account | None) -> _Meta:
    return {
        "id": version.public_id,
        "effective_from": version.effective_from,
        "effective_to": version.effective_to,
        "changed_by": _changer(account),
        "note": version.note,
    }


def _fee(view: VersionView[PolicyVersion]) -> FeePolicyVersionInfo:
    row = view.version
    assert isinstance(row, FeePolicyVersion)  # noqa: S101 - the fee policy's view
    return FeePolicyVersionInfo(
        **_meta(row, view.changed_by),
        rate_bps=row.rate_bps,
        basis=FeeBasis(row.basis),
        gst_rate_bps=row.gst_rate_bps,
        gst_mode=GstMode(row.gst_mode),
    )


def _booking(view: VersionView[PolicyVersion]) -> BookingPolicyVersionInfo:
    row = view.version
    assert isinstance(row, BookingPolicyVersion)  # noqa: S101 - the booking policy's view
    return BookingPolicyVersionInfo(
        **_meta(row, view.changed_by),
        token_paise=row.token_paise,
        hold_minutes=row.hold_minutes,
        free_cancel_days=row.free_cancel_days,
        check_window_hours=row.check_window_hours,
        confirm_deadline_hours=row.confirm_deadline_hours,
        no_show_days=row.no_show_days,
        late_cancel_policy=LateCancelPolicy(row.late_cancel_policy),
        max_active_holds_per_user=row.max_active_holds_per_user,
        max_advance_days=row.max_advance_days,
    )


def _caps(view: VersionView[PolicyVersion]) -> PricingCapsVersionInfo:
    row = view.version
    assert isinstance(row, PricingCapsVersion)  # noqa: S101 - the caps' view
    return PricingCapsVersionInfo(
        **_meta(row, view.changed_by),
        max_premium_bps=row.max_premium_bps,
        max_discount_bps=row.max_discount_bps,
        rounding_step_paise=row.rounding_step_paise,
    )


def _band(view: BandView) -> RentBandInfo:
    band = view.band
    return RentBandInfo(
        **_meta(band, view.changed_by),
        locality=BandLocality(slug=view.locality.slug, name=view.locality.name),
        occupancy=Occupancy(band.occupancy),
        min_rent_paise=band.min_rent_paise,
        max_rent_paise=band.max_rent_paise,
        source=BandSource(band.source),
        reference=band.reference,
    )


@router.get("/admin/policies", summary="The policies in force, for admins")
async def admin_policies(actor: CurrentActor, db: DbSession, clock: ClockDep) -> AdminPolicies:
    """Admins, in a staff session: each policy's version in force, since when and by whom."""
    _admin(actor)
    found = await PolicyService(db, clock).in_force()
    return AdminPolicies(
        fee=_fee(found[PolicyKind.FEE]),
        booking=_booking(found[PolicyKind.BOOKING]),
        caps=_caps(found[PolicyKind.CAPS]),
    )


@router.get("/admin/policies/history", summary="The policies' latest versions")
async def policy_history(actor: CurrentActor, db: DbSession, clock: ClockDep) -> PolicyHistory:
    """Admins: each policy's last 20 versions, newest first."""
    _admin(actor)
    found = await PolicyService(db, clock).history()
    return PolicyHistory(
        fee=[_fee(view) for view in found[PolicyKind.FEE]],
        booking=[_booking(view) for view in found[PolicyKind.BOOKING]],
        caps=[_caps(view) for view in found[PolicyKind.CAPS]],
    )


@router.post("/admin/policies/fee", summary="Change the placement fee")
async def change_fee(
    body: FeePolicyInput, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> FeePolicyVersionInfo:
    """Admins: the fee from now on; quotes and bookings made before keep theirs (rule 5).
    Audited. 422 POLICY_INVALID names what's wrong."""
    _admin(actor)
    policy = FeePolicy(
        rate_bps=BasisPoints(body.rate_bps),
        basis=body.basis,
        gst_rate_bps=BasisPoints(body.gst_rate_bps),
        gst_mode=body.gst_mode,
    )
    return _fee(await PolicyService(db, clock).change_fee(actor, policy, note=body.note))


@router.post("/admin/policies/booking", summary="Change the booking terms")
async def change_booking(
    body: BookingPolicyInput, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> BookingPolicyVersionInfo:
    """Admins: the token, hold, cancellation and check-window terms from now on. A token stays
    from ₹1,000 to ₹2,000 (rule 8). Audited. 422 POLICY_INVALID names what's wrong."""
    _admin(actor)
    policy = BookingPolicy(
        token_paise=Paise(body.token_paise),
        hold_minutes=body.hold_minutes,
        free_cancel_days=body.free_cancel_days,
        check_window_hours=body.check_window_hours,
        confirm_deadline_hours=body.confirm_deadline_hours,
        no_show_days=body.no_show_days,
        late_cancel_policy=body.late_cancel_policy,
        max_active_holds_per_user=body.max_active_holds_per_user,
        max_advance_days=body.max_advance_days,
    )
    return _booking(await PolicyService(db, clock).change_booking(actor, policy, note=body.note))


@router.post("/admin/policies/caps", summary="Change the caps on dynamic prices")
async def change_caps(
    body: PricingCapsInput, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> PricingCapsVersionInfo:
    """Admins: how far dynamic prices may move from the listed rent, and their rounding step,
    from now on (rule 6). Audited. 422 POLICY_INVALID names what's wrong."""
    _admin(actor)
    caps = PricingCaps(
        max_premium_bps=BasisPoints(body.max_premium_bps),
        max_discount_bps=BasisPoints(body.max_discount_bps),
        rounding_step_paise=Paise(body.rounding_step_paise),
    )
    return _caps(await PolicyService(db, clock).change_caps(actor, caps, note=body.note))


@router.get("/admin/rent-bands", summary="Rent bands")
async def rent_bands(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    locality: LocalityFilter = None,
    *,
    ended: bool = False,
) -> RentBandList:
    """Admins: the bands in force, newest first (with ``ended``, past ones too), for one
    locality if asked."""
    _admin(actor)
    views = await RentBandService(db, clock).listed(locality=locality, ended=ended)
    return RentBandList(items=[_band(view) for view in views])


@router.post("/admin/rent-bands", status_code=status.HTTP_201_CREATED, summary="Set a rent band")
async def set_rent_band(
    body: RentBandInput, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RentBandInfo:
    """Admins: a locality's band for one occupancy from now on, ending the one in force (rule
    6). Audited. 422 POLICY_INVALID names what's wrong."""
    _admin(actor)
    band = RentBand(
        min_rent_paise=Paise(body.min_rent_paise),
        max_rent_paise=Paise(body.max_rent_paise),
        source=body.source,
        reference=body.reference,
    )
    view = await RentBandService(db, clock).set(
        actor, locality=body.locality, occupancy=body.occupancy, band=band, note=body.note
    )
    return _band(view)


@router.post("/admin/rent-bands/{band_id}/end", summary="End a rent band")
async def end_rent_band(
    band_id: uuid.UUID, body: RentBandEnd, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RentBandInfo:
    """Admins: no band for its locality and occupancy from now. Audited. 409
    INVALID_TRANSITION for one already ended."""
    _admin(actor)
    return _band(await RentBandService(db, clock).end(actor, band_id, note=body.note))
