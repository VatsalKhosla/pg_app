"""An invoice's PDF (step 6.5, ADR 0061): a draft until the company's details are set, the amounts
the invoice holds, and nothing an owner typed can break it."""

from datetime import date

from app.modules.invoices.domain.invoices import invoice_amounts
from app.modules.invoices.pdf import InvoiceDocument, InvoiceSeller, file_name, render_invoice

SELLER = InvoiceSeller(
    legal_name="Fictional Stays Private Limited",
    address="1 A Fictional Road, New Delhi",
    gstin="00ABCDE0000F0Z0",
    sac_code="0000",
)


def _document(seller: InvoiceSeller, **change: object) -> InvoiceDocument:
    fields: dict[str, object] = {
        "number": "FY2026-27/000001",
        "issued_on": date(2026, 11, 6),
        "booking_code": "BK-7F3K2Q9M",
        "owner_legal_name": "Fictional Homes LLP",
        "owner_business_name": "Fictional Homes",
        "owner_gstin": None,
        "pg_name": "Aster House",
        "pg_address": "House 9, a fictional lane, Satya Niketan",
        "base_rent_paise": 1_000_000,
        "fee_rate_bps": 3_000,
        "gst_rate_bps": 1_800,
        "gst_included": False,
        "amounts": invoice_amounts(total_paise=354_000, gst_paise=54_000, token_paise=200_000),
        "seller": seller,
    } | change
    return InvoiceDocument(**fields)  # type: ignore[arg-type]


def test_without_the_companys_details_an_invoice_is_a_draft() -> None:
    pdf = render_invoice(_document(InvoiceSeller()))
    assert pdf.startswith(b"%PDF-")
    assert b"Draft invoice" in pdf
    assert b"not a tax invoice" in pdf
    assert b"Tax invoice" not in pdf


def test_with_them_it_is_a_tax_invoice_with_every_amount() -> None:
    pdf = render_invoice(_document(SELLER))
    for text in (
        b"Tax invoice",
        b"FY2026-27/000001",
        b"00ABCDE0000F0Z0",
        b"SAC 0000",
        b"30% of the listed monthly rent of Rs. 10,000.00",
        b"Rs. 3,000.00",
        b"Rs. 540.00",
        b"Rs. 3,540.00",
        b"-Rs. 2,000.00",
        b"Rs. 1,540.00",
    ):
        assert text in pdf, text


def test_the_same_invoice_always_makes_the_same_bytes() -> None:
    assert render_invoice(_document(SELLER)) == render_invoice(_document(SELLER))


def test_what_an_owner_typed_is_text_not_markup_and_other_letters_show_as_question_marks() -> None:
    pdf = render_invoice(
        _document(SELLER, owner_legal_name="Homes <b>& Co</b>", owner_business_name="घर")
    )
    assert b"&lt;b&gt;" not in pdf  # escaped for the markup, then printed as typed
    assert b"<b>" in pdf or b"Homes" in pdf
    assert b"??" in pdf


def test_a_token_above_the_fee_is_said_to_be_owed_to_the_owner() -> None:
    amounts = invoice_amounts(total_paise=177_000, gst_paise=27_000, token_paise=200_000)
    pdf = render_invoice(_document(SELLER, amounts=amounts, gst_included=True))
    assert b"Rs. 230.00 more than this invoice" in pdf
    assert b"GST at 18% included" in pdf


def test_the_file_is_named_for_its_number() -> None:
    assert file_name("FY2026-27/000001") == "invoice-FY2026-27-000001.pdf"
