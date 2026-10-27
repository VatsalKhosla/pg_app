"""Owner routes (ARCHITECTURE §15, ADR 0021, 0025): ops add, find and edit owners and see their
agreement acceptances; owners, signed in by phone, read their own record and accept the owner
agreement.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError, NotFoundError
from app.core.pagination import PageParams
from app.core.ratelimit import client_ip
from app.modules.catalog.models import OwnerAgreement
from app.modules.catalog.policies import can_act_as_owner
from app.modules.catalog.router.listings import (
    SearchText,
    current_agreement,
    owner_info,
    require_listing_staff,
)
from app.modules.catalog.schemas import (
    AcceptanceCreate,
    AcceptanceInfo,
    AcceptanceList,
    AgreementInfo,
    OwnerCreate,
    OwnerInfo,
    OwnerPage,
    OwnerUpdate,
)
from app.modules.catalog.service import AgreementService, OwnerChanges, OwnerService

router = APIRouter(prefix="/v1", tags=["catalog"])

CurrentAgreement = Annotated[str, Depends(current_agreement)]


def _agreements(request: Request, db: DbSession, clock: ClockDep) -> AgreementService:
    return AgreementService(
        db,
        clock,
        library=request.app.state.agreements,
        current_version=current_agreement(request),
    )


def _owner_only(actor: CurrentActor) -> None:
    if not can_act_as_owner(actor):
        raise ForbiddenError


def _acceptance(row: OwnerAgreement) -> AcceptanceInfo:
    return AcceptanceInfo(
        version=row.version,
        document_sha256=row.document_sha256,
        accepted_at=row.accepted_at,
        ip=row.accepted_ip,
        user_agent=row.accepted_user_agent,
    )


# Ops.


@router.get("/ops/owners", summary="Owners, to choose one for a listing")
async def owners(
    actor: CurrentActor,
    page: PageParams,
    *,
    db: DbSession,
    clock: ClockDep,
    agreement: CurrentAgreement,
    q: SearchText = None,
) -> OwnerPage:
    """By phone number (exactly) or by name (any part)."""
    require_listing_staff(actor)
    found, next_cursor = await OwnerService(db, clock).page(page, text=q)
    return OwnerPage(
        items=[owner_info(record, current_agreement=agreement) for record in found],
        next_cursor=next_cursor,
    )


@router.post("/ops/owners", status_code=status.HTTP_201_CREATED, summary="Add an owner")
async def add_owner(
    body: OwnerCreate,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    agreement: CurrentAgreement,
) -> OwnerInfo:
    """Makes the owner's account from their phone if they haven't signed in yet."""
    require_listing_staff(actor)
    record = await OwnerService(db, clock).add(
        actor,
        phone=body.phone,
        legal_name=body.legal_name,
        business_name=body.business_name,
        gstin=body.gstin,
        name=body.name,
    )
    return owner_info(record, current_agreement=agreement)


@router.get("/ops/owners/{owner_id}", summary="An owner")
async def owner(
    owner_id: uuid.UUID,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    agreement: CurrentAgreement,
) -> OwnerInfo:
    require_listing_staff(actor)
    return owner_info(await OwnerService(db, clock).get(owner_id), current_agreement=agreement)


@router.patch("/ops/owners/{owner_id}", summary="Change an owner's business details")
async def update_owner(
    owner_id: uuid.UUID,
    body: OwnerUpdate,
    *,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    agreement: CurrentAgreement,
) -> OwnerInfo:
    """Only the fields sent change; `gstin: null` clears it."""
    require_listing_staff(actor)
    sent = body.model_fields_set
    changes: OwnerChanges = {}
    if "legal_name" in sent and body.legal_name is not None:
        changes["legal_name"] = body.legal_name
    if "business_name" in sent and body.business_name is not None:
        changes["business_name"] = body.business_name
    if "gstin" in sent:
        changes["gstin"] = body.gstin
    record = await OwnerService(db, clock).update(actor, owner_id, changes)
    return owner_info(record, current_agreement=agreement)


@router.get("/ops/owners/{owner_id}/agreements", summary="An owner's agreement acceptances")
async def owner_agreements(
    owner_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> AcceptanceList:
    """Newest first: the version, the text's hash, when, the IP and the user agent."""
    require_listing_staff(actor)
    rows = await _agreements(request, db, clock).history(owner_id)
    return AcceptanceList(items=[_acceptance(row) for row in rows])


# Owners themselves.


@router.get("/owner/profile", summary="The signed-in owner's record")
async def my_owner_profile(
    actor: CurrentActor, db: DbSession, clock: ClockDep, agreement: CurrentAgreement
) -> OwnerInfo:
    """404 for an owner whose business record hasn't been made yet (ops add it)."""
    _owner_only(actor)
    record = await OwnerService(db, clock).of_user(actor.user_id)
    if record is None:
        raise NotFoundError
    return owner_info(record, current_agreement=agreement)


@router.get("/owner/agreement", summary="The owner agreement, and whether it's accepted")
async def my_agreement(
    request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> AgreementInfo:
    _owner_only(actor)
    standing = await _agreements(request, db, clock).standing(actor)
    return AgreementInfo(
        version=standing.agreement.version,
        text=standing.agreement.text,
        document_sha256=standing.agreement.sha256,
        accepted=standing.accepted,
        accepted_at=standing.accepted_at,
        accepted_version=standing.accepted_version,
    )


@router.post(
    "/owner/agreement/acceptances",
    status_code=status.HTTP_201_CREATED,
    summary="Accept the owner agreement",
)
async def accept_agreement(
    body: AcceptanceCreate,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> AcceptanceInfo:
    """Names the version and the text's hash the owner was shown: if the agreement changed since,
    409 AGREEMENT_CHANGED, and the owner reads the new one."""
    _owner_only(actor)
    row = await _agreements(request, db, clock).accept(
        actor,
        version=body.version,
        document_sha256=body.document_sha256,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _acceptance(row)
