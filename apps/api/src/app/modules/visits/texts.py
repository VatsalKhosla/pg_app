"""The text messages visits send (ADR 0033): the wording each DLT template is registered with,
and its blanks. Messages are the student's; the address goes only once a visit is booked
(CLAUDE.md rule 11)."""

from typing import Final

SCHEDULED: Final = "visit_scheduled"
REMINDER: Final = "visit_reminder"
CANCELLED: Final = "visit_cancelled"

TEMPLATES: Final = {
    SCHEDULED: (
        "{brand}: your visit to {pg} is booked for {when}. Address: {address}. Our field agent "
        "will meet you there."
    ),
    REMINDER: "{brand}: a reminder that your visit to {pg} is at {when}. Address: {address}.",
    CANCELLED: (
        "{brand}: your visit to {pg} on {when} is cancelled. You can ask for another time on "
        "our site."
    ),
}
