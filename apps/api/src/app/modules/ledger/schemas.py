"""What the ledger's API gives (step 6.4, ADR 0060). Only ops read it, and nothing here writes."""

import uuid
from datetime import datetime

from app.core.schemas import ApiModel
from app.modules.ledger.domain.ledger import Account, AccountType, Direction, PostingKind


class TrialBalanceLine(ApiModel):
    account: Account
    name: str
    type: AccountType
    debit_paise: int
    credit_paise: int
    # Debits less credits.
    balance_paise: int


class TrialBalance(ApiModel):
    """Every account, or what one booking did to each. Debits always equal credits."""

    booking: str | None
    lines: list[TrialBalanceLine]
    total_debit_paise: int
    total_credit_paise: int


class LedgerEntryView(ApiModel):
    account: Account
    name: str
    direction: Direction
    amount_paise: int


class LedgerTransactionView(ApiModel):
    id: uuid.UUID
    kind: PostingKind
    booking: str | None
    memo: str
    posted_at: datetime
    entries: list[LedgerEntryView]


class LedgerPage(ApiModel):
    items: list[LedgerTransactionView]
    next_cursor: uuid.UUID | None
