"""The text messages grievances send (ADR 0034): the wording each DLT template is registered
with, and its blanks. Only to a signed-in complainant's own phone, never to a number someone
typed into the form."""

from typing import Final

RECEIVED: Final = "grievance_received"
ACKNOWLEDGED: Final = "grievance_acknowledged"
RESOLVED: Final = "grievance_resolved"

TEMPLATES: Final = {
    RECEIVED: (
        "{brand}: we've received your complaint, ticket {ticket}. Our grievance officer will "
        "reply by {acknowledge_by} and resolve it by {resolve_by}."
    ),
    ACKNOWLEDGED: (
        "{brand}: our grievance officer has replied about ticket {ticket} and will resolve it by "
        "{resolve_by}. The reply is on our grievances page."
    ),
    RESOLVED: (
        "{brand}: your complaint, ticket {ticket}, is resolved. What we did is on our grievances "
        "page."
    ),
}
