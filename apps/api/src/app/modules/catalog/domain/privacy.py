"""What the public may learn about a PG (ARCHITECTURE §10.5, ADR 0026).

Anyone sees a listing's display point, never its exact point, address or the owner's phone. Those
show to someone signed in, and only while ``hide_owner_contact`` is off (pending legal advice) or
once they're entitled: a visit scheduled (step 3.7) or a booking confirmed (Phase 5). Owners can't
put their number in the listing's text either, since that text is public.
"""

from app.core.pii import contains_phone


def contact_shown(*, hide_owner_contact: bool, entitled: bool) -> bool:
    """Whether a signed-in person sees the owner's phone, the address and the exact point."""
    return entitled or not hide_owner_contact


def phone_problems(name: str, value: str) -> list[str]:
    """Public text (a name, the description, a house rule, a label) can't carry a phone number."""
    if contains_phone(value):
        return [f"{name} can't include a phone number: owners' numbers show only after a visit"]
    return []
