"""The owner's side of a listing (ARCHITECTURE §15; Phase 7, ADR 0063): an owner's PGs and the
licence and society permission they upload for each, which ops read and answer; and the beacon a
PG's page sends when it's opened."""

import uuid
from datetime import timedelta
from typing import Final

from fastapi import APIRouter, Request, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError, NotFoundError
from app.core.ratelimit import RateLimit, client_ip, enforce
from app.modules.catalog.domain.listing import LicenceStatus, PropertyStatus, VerificationStatus
from app.modules.catalog.policies import can_act_as_owner, can_review_documents
from app.modules.catalog.router.listings import current_listing
from app.modules.catalog.schemas import (
    DocumentCreate,
    DocumentFile,
    DocumentInfo,
    DocumentList,
    DocumentReview,
    ListingInfo,
    OwnedPropertyInfo,
    OwnedPropertyList,
)
from app.modules.catalog.service import CatalogLookup
from app.modules.catalog.service.owner_area import DocumentView, ListingViews, PropertyDocuments

router = APIRouter(prefix="/v1", tags=["catalog"])

# A person reads a few dozen PG pages an hour at most; a script reading more counts no more.
VIEWS_PER_IP: Final = RateLimit("listing-views-per-ip", limit=120, window=timedelta(hours=1))


def _owner(actor: CurrentActor) -> None:
    if not can_act_as_owner(actor):
        raise ForbiddenError


def _ops(actor: CurrentActor) -> None:
    if not can_review_documents(actor):
        raise ForbiddenError


def _documents(request: Request, db: DbSession, clock: ClockDep) -> PropertyDocuments:
    return PropertyDocuments(db, clock, request.app.state.media_buckets, request.app.state.storage)


def _info(view: DocumentView) -> DocumentInfo:
    return DocumentInfo(
        id=view.public_id,
        kind=view.kind,
        status=view.status,
        added_at=view.added_at,
        reviewed_at=view.reviewed_at,
        note=view.note,
        files=[DocumentFile(content_type=kind, url=url) for kind, url in view.files],
    )


@router.get("/owner/properties", summary="Your PGs")
async def my_properties(actor: CurrentActor, db: DbSession) -> OwnedPropertyList:
    """By name, whatever their status: none until ops have added the owner's first."""
    _owner(actor)
    async with db.begin():
        found = await CatalogLookup(db).owned_properties(actor.user_id)
    return OwnedPropertyList(
        items=[
            OwnedPropertyInfo(
                id=row.public_id,
                slug=row.slug,
                name=row.name,
                locality=row.locality,
                status=PropertyStatus(row.status),
                verification_status=VerificationStatus(row.verification_status),
                licence_status=LicenceStatus(row.licence_status),
            )
            for row in found
        ]
    )


@router.get("/owner/properties/{property_id}", summary="Your PG in full")
async def my_property(
    property_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession
) -> ListingInfo:
    """As ops keep it: its rooms, beds, rents and charges. Anyone else's PG is a 404."""
    _owner(actor)
    async with db.begin():
        owned = await CatalogLookup(db).owned_property(actor.user_id, property_id)
    if owned is None:
        raise NotFoundError
    return await current_listing(request, db, property_id)


@router.get("/owner/properties/{property_id}/documents", summary="Your PG's documents")
async def my_documents(
    property_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> DocumentList:
    """Newest first, each with ops' word on it once they've looked. Anyone else's PG is a 404."""
    _owner(actor)
    views = await _documents(request, db, clock).mine(actor, property_id)
    return DocumentList(items=[_info(view) for view in views])


@router.post(
    "/owner/properties/{property_id}/documents",
    status_code=status.HTTP_201_CREATED,
    summary="Add a licence or society permission",
)
async def add_document(
    property_id: uuid.UUID,
    body: DocumentCreate,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> DocumentInfo:
    """A file the owner uploaded as a document (``POST /v1/media``, purpose ``document``), for ops
    to look at. 422 DOCUMENT_INVALID for one that isn't theirs or isn't a document. Audited."""
    _owner(actor)
    view = await _documents(request, db, clock).add(
        actor, property_id, kind=body.kind, media=body.media
    )
    return _info(view)


@router.get("/ops/properties/{property_id}/documents", summary="A PG's documents")
async def ops_documents(
    property_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> DocumentList:
    _ops(actor)
    views = await _documents(request, db, clock).for_ops(property_id)
    return DocumentList(items=[_info(view) for view in views])


@router.post("/ops/documents/{document_id}/review", summary="Accept or refuse a document")
async def review_document(
    document_id: uuid.UUID,
    body: DocumentReview,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> DocumentInfo:
    """Once: 409 INVALID_TRANSITION if it's been looked at already. Audited."""
    _ops(actor)
    view = await _documents(request, db, clock).review(
        actor, document_id, accepted=body.accepted, note=body.note
    )
    return _info(view)


@router.post(
    "/listings/{slug}/views",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="A PG's page was opened",
)
async def count_view(slug: str, request: Request, db: DbSession, clock: ClockDep) -> None:
    """What the page sends as it opens, for its owner's insights (step 7.6). Anyone may send it,
    120 an hour from one address; a PG that isn't live is a 404."""
    await enforce(request.app.state.rate_limiter, VIEWS_PER_IP, f"ip:{client_ip(request)}")
    await ListingViews(db, clock).count(slug)
