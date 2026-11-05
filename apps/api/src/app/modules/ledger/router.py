"""The ledger's routes (ARCHITECTURE §9.4; step 6.4, ADR 0060): ops read the books. Nothing here
writes: postings come only from the money events themselves."""

from typing import Annotated, Final

from fastapi import APIRouter, Query

from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.pagination import PageParams
from app.modules.ledger.policies import can_read_ledger
from app.modules.ledger.schemas import LedgerPage, TrialBalance
from app.modules.ledger.service import LedgerReader

router = APIRouter(prefix="/v1", tags=["ledger"])

CODE_MAX_LENGTH: Final = 32


def _ops(actor: CurrentActor) -> None:
    if not can_read_ledger(actor):
        raise ForbiddenError


@router.get("/ops/ledger/trial-balance", summary="What every account holds")
async def trial_balance(
    actor: CurrentActor,
    db: DbSession,
    booking: Annotated[str | None, Query(max_length=CODE_MAX_LENGTH)] = None,
) -> TrialBalance:
    """Debits and credits for each account, of one booking if asked. They always add up: the
    database refuses anything else."""
    _ops(actor)
    return await LedgerReader(db).trial_balance(booking)


@router.get("/ops/ledger/transactions", summary="What was posted")
async def ledger_transactions(
    actor: CurrentActor,
    *,
    page: PageParams,
    db: DbSession,
    booking: Annotated[str | None, Query(max_length=CODE_MAX_LENGTH)] = None,
) -> LedgerPage:
    """Newest first, of one booking if asked."""
    _ops(actor)
    items, next_cursor = await LedgerReader(db).page(page, booking=booking)
    return LedgerPage(items=items, next_cursor=next_cursor)
