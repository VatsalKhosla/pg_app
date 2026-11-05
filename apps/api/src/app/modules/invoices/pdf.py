"""An invoice's PDF (ARCHITECTURE §9.5; step 6.5, ADR 0061), made once by a job and kept in the
private bucket. The same invoice always makes the same bytes.

Until the company's registered name, address, GSTIN and SAC code are set, the invoice says it's a
draft, and isn't a tax invoice: those are facts for the founders and their accountant, never ours
to invent. ReportLab's built-in fonts carry Western European letters only, so any other letter in a
name prints as a question mark rather than vanishing, and amounts are in "Rs.".
"""

import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Self
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import BRAND_NAME
from app.core.money import format_inr
from app.modules.invoices.domain.invoices import percent

if TYPE_CHECKING:
    from datetime import date

    from app.config import Settings
    from app.modules.invoices.domain.invoices import InvoiceAmounts

_MARGIN: Final = 18 * mm
_LINE: Final = colors.HexColor("#9ca3af")


@dataclass(frozen=True, slots=True)
class InvoiceSeller:
    """Who the invoice is from, as the company's accountant gives it."""

    legal_name: str | None = None
    address: str | None = None
    gstin: str | None = None
    sac_code: str | None = None

    @property
    def complete(self) -> bool:
        return None not in (self.legal_name, self.address, self.gstin, self.sac_code)

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            legal_name=settings.invoice_seller_name,
            address=settings.invoice_seller_address,
            gstin=settings.invoice_seller_gstin,
            sac_code=settings.invoice_sac_code,
        )


@dataclass(frozen=True, slots=True)
class InvoiceDocument:
    number: str
    issued_on: date
    booking_code: str
    owner_legal_name: str
    owner_business_name: str
    owner_gstin: str | None
    pg_name: str
    pg_address: str
    base_rent_paise: int
    fee_rate_bps: int
    gst_rate_bps: int
    gst_included: bool
    amounts: InvoiceAmounts
    seller: InvoiceSeller


def rupees(paise: int) -> str:
    return format_inr(paise).replace("₹", "Rs. ")


def _text(value: str) -> str:
    """Safe in a paragraph's markup, in letters the built-in fonts have."""
    return escape(value.encode("cp1252", "replace").decode("cp1252"))


def file_name(number: str) -> str:
    return f"invoice-{number.replace('/', '-')}.pdf"


def render_invoice(document: InvoiceDocument) -> bytes:
    seller = document.seller
    amounts = document.amounts
    title = "Tax invoice" if seller.complete else "Draft invoice"
    styles = getSampleStyleSheet()
    body, small, heading = styles["BodyText"], styles["Italic"], styles["Title"]

    def para(text: str, style: object = body) -> Paragraph:
        return Paragraph(text, style)  # type: ignore[arg-type]

    seller_lines = (
        [
            f"<b>{_text(seller.legal_name or '')}</b> ({_text(BRAND_NAME)})",
            _text(seller.address or ""),
            f"GSTIN {_text(seller.gstin or '')}",
        ]
        if seller.complete
        else [
            f"<b>{_text(BRAND_NAME)}</b>",
            "Draft: the company's registered name, address and GSTIN are still to be added, "
            "so this is not a tax invoice.",
        ]
    )
    to_lines = [
        f"<b>{_text(document.owner_legal_name)}</b>",
        _text(document.owner_business_name),
        "GSTIN " + _text(document.owner_gstin) if document.owner_gstin else "No GSTIN given",
    ]
    fee_terms = (
        f"{percent(document.fee_rate_bps)} of the listed monthly rent of "
        f"{rupees(document.base_rent_paise)}"
        + (f", GST at {percent(document.gst_rate_bps)} included" if document.gst_included else "")
    )
    service = "Placement of a tenant at " + _text(document.pg_name)
    if seller.sac_code is not None:
        service += f" (SAC {_text(seller.sac_code)})"
    rows: list[list[object]] = [
        ["", "Amount"],
        [para(f"{service}<br/>{_text(document.pg_address)}<br/>{fee_terms}"), ""],
        ["Placement fee", rupees(amounts.fee_paise)],
        [f"GST at {percent(document.gst_rate_bps)}", rupees(amounts.gst_paise)],
        ["Total", rupees(amounts.total_paise)],
        ["Paid by the student's token", "-" + rupees(amounts.token_applied_paise)],
        ["Balance due", rupees(amounts.balance_due_paise)],
    ]
    table = Table(rows, colWidths=[None, 40 * mm])
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, _LINE),
                ("LINEABOVE", (0, 4), (-1, 4), 0.5, _LINE),
                ("LINEABOVE", (0, -1), (-1, -1), 0.5, _LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story: list[object] = [
        para(title, heading),
        para(f"Invoice number <b>{_text(document.number)}</b>"),
        para(f"Date {document.issued_on.strftime('%d %B %Y')}"),
        para(f"Booking {_text(document.booking_code)}"),
        Spacer(1, 6 * mm),
        para("From"),
        *(para(line) for line in seller_lines),
        Spacer(1, 4 * mm),
        para("To"),
        *(para(line) for line in to_lines),
        Spacer(1, 6 * mm),
        table,
        Spacer(1, 6 * mm),
    ]
    if amounts.token_over_paise > 0:
        story.append(
            para(
                f"The student's token came to {rupees(amounts.token_over_paise)} more than this "
                "invoice. That is owed to you, and reaches you through the payment gateway's "
                "settlement, never through our own account.",
                small,
            )
        )
    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=f"{title} {document.number}",
        author=BRAND_NAME,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        # The same bytes every time, and the words readable by a test.
        invariant=1,
        pageCompression=0,
    ).build(story)  # type: ignore[arg-type]
    return buffer.getvalue()
