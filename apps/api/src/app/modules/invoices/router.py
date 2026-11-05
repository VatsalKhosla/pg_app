"""Invoice routes (ARCHITECTURE §9.5, §15; step 6.5, ADR 0061): owners read their own, ops read
everyone's, and each PDF is behind a link that works for 5 minutes. Nothing here issues one: a
booking does, as it settles."""

import uuid
from typing import Annotated, Any, Final

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import RedirectResponse

from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.pagination import PageParams
from app.modules.invoices.domain.invoices import InvoiceStatus
from app.modules.invoices.policies import can_see_invoices, can_see_own_invoices
from app.modules.invoices.schemas import InvoicePage, OpsInvoicePage
from app.modules.invoices.service import InvoiceReader

router = APIRouter(prefix="/v1", tags=["invoices"])

CODE_MAX_LENGTH: Final = 32
_TO_THE_FILE: Final[dict[int | str, dict[str, Any]]] = {
    status.HTTP_303_SEE_OTHER: {"description": "To the PDF, by a link that works for 5 minutes"}
}


def _reader(request: Request, db: DbSession) -> InvoiceReader:
    return InvoiceReader(db, request.app.state.storage, request.app.state.media_buckets)


def _to(url: str) -> RedirectResponse:
    return RedirectResponse(
        url, status_code=status.HTTP_303_SEE_OTHER, headers={"Cache-Control": "no-store"}
    )


@router.get("/owner/invoices", summary="Your invoices")
async def my_invoices(
    request: Request, actor: CurrentActor, *, page: PageParams, db: DbSession
) -> InvoicePage:
    """Newest first: what each placement's fee came to, what the token paid, and what's due."""
    if not can_see_own_invoices(actor):
        raise ForbiddenError
    items, next_cursor = await _reader(request, db).mine(actor, page)
    return InvoicePage(items=items, next_cursor=next_cursor)


@router.get(
    "/owner/invoices/{invoice_id}/file",
    summary="Download your invoice",
    status_code=status.HTTP_303_SEE_OTHER,
    response_class=RedirectResponse,
    responses=_TO_THE_FILE,
)
async def my_invoice_file(
    invoice_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession
) -> RedirectResponse:
    """404 for anyone else's, and until its PDF is made."""
    if not can_see_own_invoices(actor):
        raise ForbiddenError
    return _to(await _reader(request, db).my_file(actor, invoice_id))


@router.get("/ops/invoices", summary="Owners' invoices")
async def ops_invoices(
    request: Request,
    actor: CurrentActor,
    *,
    page: PageParams,
    db: DbSession,
    invoice_status: Annotated[InvoiceStatus | None, Query(alias="status")] = None,
    booking: Annotated[str | None, Query(max_length=CODE_MAX_LENGTH)] = None,
) -> OpsInvoicePage:
    """Newest first; of one status, or one booking's, if asked."""
    if not can_see_invoices(actor):
        raise ForbiddenError
    items, next_cursor = await _reader(request, db).for_ops(
        page, status=invoice_status, booking=booking
    )
    return OpsInvoicePage(items=items, next_cursor=next_cursor)


@router.get(
    "/ops/invoices/{invoice_id}/file",
    summary="Download an owner's invoice",
    status_code=status.HTTP_303_SEE_OTHER,
    response_class=RedirectResponse,
    responses=_TO_THE_FILE,
)
async def ops_invoice_file(
    invoice_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession
) -> RedirectResponse:
    if not can_see_invoices(actor):
        raise ForbiddenError
    return _to(await _reader(request, db).file(invoice_id))
