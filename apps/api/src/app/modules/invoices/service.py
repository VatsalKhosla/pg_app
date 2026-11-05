"""Owners' invoices (ARCHITECTURE §9.5; step 6.5, ADR 0061).

- **Issued** inside the change that settles a booking (the state machine's IssueOwnerInvoice): the
  year's next number, the posting, and jobs for the PDF, the owner's text and the balance's link.
- **Paid** when the gateway says so: the payments module tells us, in the transaction that posts
  the money.
- **Read** by the owner it's for, and by ops, the PDF behind a link that works for 5 minutes.

This module knows neither bookings nor payments: bookings and payments call it.
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.config import BRAND_NAME
from app.core import audit
from app.core.calendar import india_date
from app.core.errors import NotFoundError
from app.core.ids import normalize_booking_code
from app.core.money import format_inr
from app.core.outbox import enqueue
from app.core.pagination import split_page
from app.modules.catalog.service import CatalogLookup
from app.modules.identity.service import Accounts
from app.modules.invoices.domain.invoices import (
    InvoiceAmounts,
    InvoiceStatus,
    financial_year,
    invoice_amounts,
    invoice_number,
    status_on_issue,
)
from app.modules.invoices.models import OwnerInvoice
from app.modules.invoices.pdf import InvoiceDocument, file_name, render_invoice
from app.modules.invoices.repository import InvoiceRepository
from app.modules.invoices.schemas import InvoiceView, OpsInvoiceView, PayLink
from app.modules.invoices.texts import ISSUED, ISSUED_PAID
from app.modules.ledger.domain.ledger import owner_invoiced
from app.modules.ledger.service import Ledger

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.pagination import PageRequest
    from app.modules.invoices.pdf import InvoiceSeller
    from app.modules.media.ports import ObjectStorage
    from app.modules.media.service import Buckets

RENDER_PDF: Final = "invoices.render_pdf"
INVOICE_TEXT: Final = "invoices.text"
# Collecting a balance is the payments module's: its job takes this one (ADR 0061).
BALANCE_DUE: Final = "invoices.balance_due"
# Private files are signed for 5 minutes (ARCHITECTURE §12).
FILE_LINK_TTL: Final = timedelta(minutes=5)

logger = structlog.stdlib.get_logger(__name__)

_issued = metrics.get_meter("app.invoices").create_counter(
    "invoices.issued", description="Owners' invoices issued, by whether anything was left to pay"
)


@dataclass(frozen=True, slots=True)
class InvoiceRequest:
    """What a settling booking knows about the invoice it owes."""

    owner_id: int
    property_id: int
    booking_id: int
    booking_code: str
    base_rent_paise: int
    fee_rate_bps: int
    gst_rate_bps: int
    gst_included: bool
    # The owner's total with its GST, and the GST, as the booking kept them from its quote.
    total_paise: int
    gst_paise: int
    token_paise: int


@dataclass(frozen=True, slots=True)
class Balance:
    """What's left to pay of an invoice, for whoever collects it."""

    id: int
    public_id: uuid.UUID
    number: str
    booking_id: int
    booking_code: str
    status: InvoiceStatus
    balance_due_paise: int


def _balance(row: OwnerInvoice) -> Balance:
    return Balance(
        id=row.id,
        public_id=row.public_id,
        number=row.number,
        booking_id=row.booking_id,
        booking_code=row.booking_code,
        status=InvoiceStatus(row.status),
        balance_due_paise=row.balance_due_paise,
    )


def _amounts(row: OwnerInvoice) -> InvoiceAmounts:
    return InvoiceAmounts(
        fee_paise=row.fee_paise,
        gst_paise=row.gst_paise,
        total_paise=row.total_paise,
        token_applied_paise=row.token_applied_paise,
        token_over_paise=row.token_over_paise,
        balance_due_paise=row.balance_due_paise,
    )


def pdf_key(row: OwnerInvoice) -> str:
    return f"invoices/{row.financial_year}/{row.public_id}.pdf"


class OwnerInvoices:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._invoices = InvoiceRepository(db)
        self._ledger = Ledger(db, clock)
        self._catalog = CatalogLookup(db)

    async def issue(self, request: InvoiceRequest) -> OwnerInvoice:
        """In the caller's transaction. A booking has one invoice: asking again gives it back."""
        found = await self._invoices.by_booking(request.booking_id)
        if found is not None:
            return found
        now = self._clock.now()
        amounts = invoice_amounts(
            total_paise=request.total_paise,
            gst_paise=request.gst_paise,
            token_paise=request.token_paise,
        )
        year = financial_year(india_date(now))
        serial = await self._invoices.next_serial(year)
        status = status_on_issue(amounts)
        invoice = OwnerInvoice(
            owner_id=request.owner_id,
            booking_id=request.booking_id,
            property_id=request.property_id,
            booking_code=request.booking_code,
            financial_year=year,
            serial=serial,
            number=invoice_number(year, serial),
            base_rent_paise=request.base_rent_paise,
            fee_rate_bps=request.fee_rate_bps,
            gst_rate_bps=request.gst_rate_bps,
            gst_included=request.gst_included,
            fee_paise=amounts.fee_paise,
            gst_paise=amounts.gst_paise,
            total_paise=amounts.total_paise,
            token_applied_paise=amounts.token_applied_paise,
            token_over_paise=amounts.token_over_paise,
            balance_due_paise=amounts.balance_due_paise,
            status=status,
            issued_at=now,
            paid_at=now if status is InvoiceStatus.PAID else None,
        )
        await self._invoices.add(invoice)
        await self._ledger.post(
            owner_invoiced(amounts.fee_paise, amounts.gst_paise),
            key=f"owner_invoiced:{invoice.public_id}",
            booking_id=request.booking_id,
            booking_code=request.booking_code,
            memo=invoice.number,
        )
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.SYSTEM,
            action="invoice.issued",
            entity_type="owner_invoice",
            entity_id=str(invoice.public_id),
            details={
                "number": invoice.number,
                "booking": request.booking_code,
                "totalPaise": amounts.total_paise,
                "balanceDuePaise": amounts.balance_due_paise,
            },
        )
        payload = {"invoice": str(invoice.public_id)}
        jobs = [RENDER_PDF, INVOICE_TEXT]
        if status is InvoiceStatus.ISSUED:
            jobs.append(BALANCE_DUE)
        for kind in jobs:
            await enqueue(
                self._db,
                kind,
                payload,
                clock=self._clock,
                dedupe_key=f"{kind}:{invoice.public_id}",
            )
        _issued.add(1, {"due": status is InvoiceStatus.ISSUED})
        return invoice

    async def balance(self, public_id: uuid.UUID) -> Balance | None:
        found = await self._invoices.by_public_id(public_id)
        return None if found is None else _balance(found)

    async def own_balance(self, actor: Actor, public_id: uuid.UUID) -> Balance:
        """The signed-in owner's own invoice; anyone else's is a 404."""
        owner_id = await self._catalog.owner_id_of_user(actor.user_id)
        found = await self._invoices.by_public_id(public_id)
        if found is None or owner_id is None or found.owner_id != owner_id:
            raise NotFoundError
        return _balance(found)

    async def balance_by_id(self, invoice_id: int) -> Balance:
        return _balance(await self._invoices.by_id(invoice_id))

    async def offer(self, invoice_id: int, *, provider: str, url: str) -> None:
        """The balance can be paid at ``url`` now."""
        invoice = await self._invoices.by_id(invoice_id, lock=True)
        if invoice.status == InvoiceStatus.ISSUED:
            invoice.pay_provider = provider
            invoice.pay_url = url

    async def withdraw(self, invoice_id: int, *, url: str | None) -> None:
        """The link at ``url`` can't be paid any more."""
        invoice = await self._invoices.by_id(invoice_id, lock=True)
        if url is None or invoice.pay_url == url:
            invoice.pay_provider = None
            invoice.pay_url = None

    async def paid(self, invoice_id: int, *, by: audit.Actor) -> bool:
        """The balance came in. Whether this marked it: False if it was paid already."""
        invoice = await self._invoices.by_id(invoice_id, lock=True)
        if invoice.status == InvoiceStatus.PAID:
            return False
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = self._clock.now()
        invoice.pay_provider = None
        invoice.pay_url = None
        await audit.record(
            self._db,
            clock=self._clock,
            actor=by,
            action="invoice.paid",
            entity_type="owner_invoice",
            entity_id=str(invoice.public_id),
            details={"number": invoice.number, "amountPaise": invoice.balance_due_paise},
        )
        return True

    async def text_for(self, public_id: uuid.UUID) -> tuple[str, str, dict[str, str]] | None:
        """The owner's phone, the template and its blanks."""
        invoice = await self._invoices.by_public_id(public_id)
        if invoice is None:
            return None
        user_id = (await self._catalog.owner_user_ids({invoice.owner_id})).get(invoice.owner_id)
        if user_id is None:
            return None
        phone = (await Accounts(self._db).many([user_id]))[user_id].phone_e164
        values = {
            "brand": BRAND_NAME,
            "number": invoice.number,
            "code": invoice.booking_code,
            "total": format_inr(invoice.total_paise),
        }
        if invoice.balance_due_paise == 0:
            return phone, ISSUED_PAID, values
        return (
            phone,
            ISSUED,
            values
            | {
                "token": format_inr(invoice.token_applied_paise),
                "balance": format_inr(invoice.balance_due_paise),
            },
        )


class InvoicePdfs:
    """Making an invoice's PDF, once, in the worker."""

    def __init__(
        self, db: AsyncSession, storage: ObjectStorage, buckets: Buckets, seller: InvoiceSeller
    ) -> None:
        self._invoices = InvoiceRepository(db)
        self._catalog = CatalogLookup(db)
        self._storage = storage
        self._buckets = buckets
        self._seller = seller

    async def make(self, public_id: uuid.UUID) -> None:
        invoice = await self._invoices.by_public_id(public_id)
        if invoice is None or invoice.pdf_key is not None:
            return
        party = await self._catalog.invoice_party(invoice.owner_id, invoice.property_id)
        document = InvoiceDocument(
            number=invoice.number,
            issued_on=india_date(invoice.issued_at),
            booking_code=invoice.booking_code,
            owner_legal_name=party.legal_name,
            owner_business_name=party.business_name,
            owner_gstin=party.gstin,
            pg_name=party.pg_name,
            pg_address=party.pg_address,
            base_rent_paise=invoice.base_rent_paise,
            fee_rate_bps=invoice.fee_rate_bps,
            gst_rate_bps=invoice.gst_rate_bps,
            gst_included=invoice.gst_included,
            amounts=_amounts(invoice),
            seller=self._seller,
        )
        pdf = await asyncio.to_thread(render_invoice, document)
        key = pdf_key(invoice)
        await self._storage.upload(
            self._buckets.private,
            key,
            pdf,
            content_type="application/pdf",
            content_disposition=f'attachment; filename="{file_name(invoice.number)}"',
        )
        locked = await self._invoices.by_public_id(public_id, lock=True)
        if locked is not None:
            locked.pdf_key = key


class InvoiceReader:
    """What owners and ops read. Each page takes the same few queries, however long."""

    def __init__(self, db: AsyncSession, storage: ObjectStorage, buckets: Buckets) -> None:
        self._db = db
        self._invoices = InvoiceRepository(db)
        self._catalog = CatalogLookup(db)
        self._storage = storage
        self._buckets = buckets

    async def mine(
        self, actor: Actor, request: PageRequest
    ) -> tuple[list[InvoiceView], uuid.UUID | None]:
        async with self._db.begin():
            owner_id = await self._catalog.owner_id_of_user(actor.user_id)
            if owner_id is None:
                return [], None
            found = await self._invoices.page(
                owner_id=owner_id,
                status=None,
                booking_code=None,
                after=request.after,
                limit=request.limit,
            )
            items, next_cursor = split_page(found, request, cursor_of=lambda row: row.public_id)
            places = await self._places(items)
        return [_view(row, places[row.property_id]) for row in items], next_cursor

    async def for_ops(
        self, request: PageRequest, *, status: InvoiceStatus | None, booking: str | None
    ) -> tuple[list[OpsInvoiceView], uuid.UUID | None]:
        code = None if booking is None else normalize_booking_code(booking)
        if booking is not None and code is None:
            return [], None
        async with self._db.begin():
            found = await self._invoices.page(
                owner_id=None,
                status=status,
                booking_code=code,
                after=request.after,
                limit=request.limit,
            )
            items, next_cursor = split_page(found, request, cursor_of=lambda row: row.public_id)
            places = await self._places(items)
            owners = await self._catalog.owner_names({row.owner_id for row in items})
        return [
            OpsInvoiceView(
                **_view(row, places[row.property_id]).model_dump(), owner=owners[row.owner_id]
            )
            for row in items
        ], next_cursor

    async def my_file(self, actor: Actor, public_id: uuid.UUID) -> str:
        """A link to the owner's own invoice's PDF; anyone else's, or one not made yet, is a 404."""
        async with self._db.begin():
            owner_id = await self._catalog.owner_id_of_user(actor.user_id)
            found = await self._invoices.by_public_id(public_id)
        if found is None or owner_id is None or found.owner_id != owner_id:
            raise NotFoundError
        return self._link(found)

    async def file(self, public_id: uuid.UUID) -> str:
        async with self._db.begin():
            found = await self._invoices.by_public_id(public_id)
        if found is None:
            raise NotFoundError
        return self._link(found)

    def _link(self, row: OwnerInvoice) -> str:
        if row.pdf_key is None:
            raise NotFoundError
        return self._storage.presign_download(
            self._buckets.private,
            row.pdf_key,
            expires_in=FILE_LINK_TTL,
            filename=file_name(row.number),
        )

    async def _places(self, rows: Sequence[OwnerInvoice]) -> dict[int, str]:
        ids: Collection[int] = {row.property_id for row in rows}
        found = await self._catalog.booking_places(ids, verified_only=False)
        return {place_id: place.name for place_id, place in found.items()}


def _view(row: OwnerInvoice, place: str) -> InvoiceView:
    return InvoiceView(
        id=row.public_id,
        number=row.number,
        booking=row.booking_code,
        place=place,
        issued_at=row.issued_at,
        base_rent_paise=row.base_rent_paise,
        fee_rate_bps=row.fee_rate_bps,
        gst_rate_bps=row.gst_rate_bps,
        gst_included=row.gst_included,
        fee_paise=row.fee_paise,
        gst_paise=row.gst_paise,
        total_paise=row.total_paise,
        token_applied_paise=row.token_applied_paise,
        token_over_paise=row.token_over_paise,
        balance_due_paise=row.balance_due_paise,
        status=InvoiceStatus(row.status),
        paid_at=row.paid_at,
        has_file=row.pdf_key is not None,
        pay=None
        if row.pay_url is None or row.pay_provider not in {"razorpay", "fake"}
        else PayLink(provider=row.pay_provider, url=row.pay_url),  # type: ignore[arg-type]
    )


async def invoices_part(db: AsyncSession, user_id: int) -> dict[str, object]:
    """An owner's invoices, for their data export (DPDP; ADR 0018)."""
    owner_id = await CatalogLookup(db).owner_id_of_user(user_id)
    if owner_id is None:
        return {}
    rows = await InvoiceRepository(db).of_owner(owner_id)
    if not rows:
        return {}
    return {
        "invoices": [
            {
                "number": row.number,
                "booking": row.booking_code,
                "issuedAt": row.issued_at.isoformat(),
                "feePaise": row.fee_paise,
                "gstPaise": row.gst_paise,
                "totalPaise": row.total_paise,
                "tokenAppliedPaise": row.token_applied_paise,
                "balanceDuePaise": row.balance_due_paise,
                "status": row.status,
                "paidAt": None if row.paid_at is None else row.paid_at.isoformat(),
            }
            for row in rows
        ]
    }
