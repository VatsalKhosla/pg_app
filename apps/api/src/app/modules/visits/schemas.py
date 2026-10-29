"""The visits API's shapes (ARCHITECTURE §11, §15; ADR 0033)."""

import uuid
from datetime import datetime
from typing import Final

from pydantic import AwareDatetime, Field

from app.core.schemas import ApiModel
from app.modules.catalog.schemas import LatLng
from app.modules.visits.domain.visits import (
    MAX_PREFERRED_STARTS,
    NOTE_MAX_LENGTH,
    CancelledBy,
    Outcome,
    StudentVisitStatus,
)

SLUG: Final = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class StudentVisitRequest(ApiModel):
    # The PG's slug, as its page has it.
    property: str = Field(pattern=SLUG, max_length=80)
    # Up to three times the student could come, each the start of a half-hour visit.
    starts: list[AwareDatetime] = Field(min_length=1, max_length=MAX_PREFERRED_STARTS)


class StudentVisitPlace(ApiModel):
    slug: str
    name: str
    locality: str


class StudentVisit(ApiModel):
    """A visit as the student sees it. The address shows on the PG's page once it's booked."""

    id: uuid.UUID
    status: StudentVisitStatus
    property: StudentVisitPlace
    preferred_starts: list[datetime]
    requested_at: datetime
    scheduled_at: datetime | None
    # The agent's first name, once booked.
    agent_name: str | None
    checked_in: bool
    outcome: Outcome | None
    cancelled_at: datetime | None
    cancelled_by: CancelledBy | None


class StudentVisitList(ApiModel):
    items: list[StudentVisit]


class VisitPerson(ApiModel):
    id: uuid.UUID
    name: str | None
    phone: str


class StaffVisitPlace(ApiModel):
    """The PG with its address and exact point: for staff, who take people there."""

    id: uuid.UUID
    slug: str
    name: str
    locality: str
    address_line: str
    location: LatLng


class VisitCheckIn(ApiModel):
    """The visit log: when the agent checked in, where their phone said they were, how sure it
    was, and how far that was from the building."""

    at: datetime
    position: LatLng
    accuracy_m: int
    distance_m: int


class StaffVisit(ApiModel):
    id: uuid.UUID
    status: StudentVisitStatus
    next_statuses: list[StudentVisitStatus]
    property: StaffVisitPlace
    student: VisitPerson
    preferred_starts: list[datetime]
    requested_at: datetime
    scheduled_at: datetime | None
    agent: VisitPerson | None
    check_in: VisitCheckIn | None
    outcome: Outcome | None
    outcome_note: str
    finished_at: datetime | None
    cancelled_at: datetime | None
    cancelled_by: CancelledBy | None
    cancel_reason: str


class StaffVisitPage(ApiModel):
    items: list[StaffVisit]
    next_cursor: uuid.UUID | None


class StaffVisitList(ApiModel):
    items: list[StaffVisit]


class VisitScheduleRequest(ApiModel):
    at: AwareDatetime
    # The field agent's id.
    agent: uuid.UUID


class VisitCheckInRequest(ApiModel):
    position: LatLng
    accuracy_m: int = Field(ge=0, le=10_000)


class VisitOutcomeRequest(ApiModel):
    outcome: Outcome
    note: str = Field(default="", max_length=NOTE_MAX_LENGTH)


class VisitCancelRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=NOTE_MAX_LENGTH)
