"""Errors of the catalog module, as problem details with stable codes (ARCHITECTURE §15)."""

from typing import TYPE_CHECKING

from app.core.errors import AppError

if TYPE_CHECKING:
    from collections.abc import Sequence


class ListingInvalidError(AppError):
    """Listing details the rules refuse, such as a base rent outside the owner's range. The
    detail names every problem at once."""

    status = 422
    code = "LISTING_INVALID"
    title = "Those listing details don't work"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class ListingIncompleteError(AppError):
    """Publishing a property with nothing to sell yet."""

    status = 409
    code = "LISTING_INCOMPLETE"
    title = "The listing isn't ready to publish"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class RoomFullError(AppError):
    status = 409
    code = "ROOM_FULL"
    title = "The room already has as many beds as its occupancy"


class OwnerExistsError(AppError):
    """That phone number's account already has an owner record."""

    status = 409
    code = "OWNER_EXISTS"
    title = "That person is already an owner"


class LabelTakenError(AppError):
    """A room label already used in its category, or a bed label in its room."""

    status = 409
    code = "LABEL_TAKEN"
    title = "That label is already used here"


class AgreementChangedError(AppError):
    """An acceptance of a version, or a text, that isn't the current agreement's: it changed after
    the owner opened it."""

    status = 409
    code = "AGREEMENT_CHANGED"
    title = "The agreement has changed; read the current version and accept that"


class ContactHiddenError(AppError):
    """The owner's phone, the address and the exact point stay hidden from this person for now
    (``hide_owner_contact``, ADR 0026): they show once a visit is scheduled or a booking is
    confirmed."""

    status = 403
    code = "CONTACT_HIDDEN"
    title = "The owner's contact details show once you've booked a visit"
