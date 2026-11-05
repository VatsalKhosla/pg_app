"""The text messages payments send (ADR 0059): the wording each DLT template is registered with,
and its blanks."""

from typing import Final

REFUND_PROCESSED: Final = "payment_refund_processed"

TEMPLATES: Final = {
    REFUND_PROCESSED: (
        "{brand}: your refund of {amount} for booking {code} has gone to your bank. It can take up "
        "to 7 working days to show in your account."
    ),
}
