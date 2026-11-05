"""What the invoices API gives (step 6.5, ADR 0061). Nothing here is written through the API: an
invoice is issued as its booking settles."""

import uuid
from datetime import datetime
from typing import Literal

from app.core.schemas import ApiModel
from app.modules.invoices.domain.invoices import InvoiceStatus


class PayLink(ApiModel):
    """Where the balance can be paid: Razorpay's page, or the fake gateway's test bank."""

    provider: Literal["razorpay", "fake"]
    url: str


class InvoiceView(ApiModel):
    id: uuid.UUID
    number: str
    booking: str
    place: str
    issued_at: datetime
    base_rent_paise: int
    fee_rate_bps: int
    gst_rate_bps: int
    # Whether the fee had its GST in it (gst_mode inclusive), rather than added to it.
    gst_included: bool
    # The fee before GST.
    fee_paise: int
    gst_paise: int
    total_paise: int
    token_applied_paise: int
    # What the token came to beyond the total: owed to the owner.
    token_over_paise: int
    balance_due_paise: int
    status: InvoiceStatus
    paid_at: datetime | None
    # Whether the PDF has been made yet.
    has_file: bool
    pay: PayLink | None


class OpsInvoiceView(InvoiceView):
    owner: str


class InvoicePage(ApiModel):
    items: list[InvoiceView]
    next_cursor: uuid.UUID | None


class OpsInvoicePage(ApiModel):
    items: list[OpsInvoiceView]
    next_cursor: uuid.UUID | None
