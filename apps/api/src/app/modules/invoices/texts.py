"""The text messages invoices send (step 6.5, ADR 0061): the wording each DLT template is
registered with, and its blanks."""

from typing import Final

ISSUED: Final = "owner_invoice_issued"
# The student's token paid the whole invoice.
ISSUED_PAID: Final = "owner_invoice_issued_paid"

TEMPLATES: Final = {
    ISSUED: (
        "{brand}: invoice {number} for booking {code} is ready. The fee comes to {total}, the "
        "student's token paid {token} of it, and {balance} is due. You can see it and pay on your "
        "{brand} owner page."
    ),
    ISSUED_PAID: (
        "{brand}: invoice {number} for booking {code} is ready. The fee comes to {total}, and the "
        "student's token paid all of it, so nothing is due."
    ),
}
