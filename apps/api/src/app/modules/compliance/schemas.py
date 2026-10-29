"""Bodies of the compliance routes (camelCase JSON, unknown fields rejected)."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import AfterValidator, Field, StringConstraints
from pydantic_core import PydanticCustomError

from app.core.human_check import MAX_TOKEN_LENGTH
from app.core.schemas import ApiModel
from app.modules.compliance.domain.grievances import (
    DETAILS_MAX_LENGTH,
    EMAIL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    REFERENCE_MAX_LENGTH,
    REPLY_MAX_LENGTH,
    GrievanceCategory,
    GrievanceStatus,
)
from app.modules.compliance.domain.requests import DataRequestKind, DataRequestStatus
from app.modules.identity.domain.phones import normalize_indian_mobile

# Enough to catch a typo; whether the address works is up to the reply.
_EMAIL: Final = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _indian_mobile(value: str) -> str:
    phone = normalize_indian_mobile(value)
    if phone is None:
        raise PydanticCustomError("phone_invalid", "Enter a 10-digit Indian mobile number.")
    return phone


def _email(value: str) -> str:
    if _EMAIL.fullmatch(value) is None:
        raise PydanticCustomError(
            "email_invalid", "Enter an email address such as name@example.com."
        )
    return value


Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class DataRequestCreate(ApiModel):
    kind: DataRequestKind


class DataRequestInfo(ApiModel):
    id: uuid.UUID
    kind: DataRequestKind
    status: DataRequestStatus
    requested_at: datetime
    resolved_at: datetime | None
    # An export's file can be downloaded until then.
    expires_at: datetime | None
    # Why a deletion was completed as it was, or rejected.
    note: str | None


class DataRequestPage(ApiModel):
    items: list[DataRequestInfo]
    next_cursor: uuid.UUID | None


class Requester(ApiModel):
    id: uuid.UUID
    phone: str
    name: str | None


class QueuedDataRequest(DataRequestInfo):
    requester: Requester | None


class DataRequestQueue(ApiModel):
    items: list[QueuedDataRequest]
    next_cursor: uuid.UUID | None


class DataRequestResolution(ApiModel):
    """Staff resolve a deletion request, saying what was done or why it was refused."""

    outcome: Literal["completed", "rejected"]
    note: str = Field(min_length=1, max_length=1000)


class GrievanceCreate(ApiModel):
    """A complaint to the grievance officer. Signed in, the account says who it's from (its phone
    is the contact); signed out, a name and a phone number or email address are needed, and a
    human check token."""

    category: GrievanceCategory
    details: Annotated[Text, Field(min_length=1, max_length=DETAILS_MAX_LENGTH)]
    # What it's about: a PG's name, a visit, a booking code.
    reference: Annotated[Text, Field(max_length=REFERENCE_MAX_LENGTH)] = ""
    name: Annotated[Text, Field(min_length=1, max_length=NAME_MAX_LENGTH)] | None = None
    phone: (
        Annotated[str, StringConstraints(max_length=32), AfterValidator(_indian_mobile)] | None
    ) = None
    email: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, max_length=EMAIL_MAX_LENGTH),
            AfterValidator(_email),
        ]
        | None
    ) = None
    human_check_token: str = Field(default="", max_length=MAX_TOKEN_LENGTH)


class GrievanceReceipt(ApiModel):
    """What the person keeps: the ticket number, and when to expect an answer."""

    ticket_number: str
    status: GrievanceStatus
    received_at: datetime
    acknowledge_by: datetime
    resolve_by: datetime


class MyGrievance(GrievanceReceipt):
    category: GrievanceCategory
    reference: str
    details: str
    acknowledged_at: datetime | None
    # The grievance officer's reply, once acknowledged; what was done, once resolved.
    reply: str
    resolved_at: datetime | None
    resolution: str


class MyGrievanceList(ApiModel):
    items: list[MyGrievance]


class Complainant(ApiModel):
    """Who complained and how to answer them. ``account`` is set when they were signed in."""

    name: str
    phone: str | None
    email: str | None
    account: uuid.UUID | None


class StaffGrievance(MyGrievance):
    complainant: Complainant
    # A step's deadline has passed with the grievance still waiting on it.
    late: bool
    next_statuses: list[GrievanceStatus]


class StaffGrievancePage(ApiModel):
    items: list[StaffGrievance]
    next_cursor: uuid.UUID | None


class GrievanceAcknowledgement(ApiModel):
    """The grievance officer's reply, which the person sees: that it's being looked at, by whom,
    and anything more they need."""

    reply: Annotated[Text, Field(min_length=1, max_length=REPLY_MAX_LENGTH)]


class GrievanceResolution(ApiModel):
    """What was done about it, which the person sees."""

    resolution: Annotated[Text, Field(min_length=1, max_length=REPLY_MAX_LENGTH)]
