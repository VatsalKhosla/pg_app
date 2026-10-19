"""Bodies of the compliance routes (camelCase JSON, unknown fields rejected)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.compliance.domain.requests import DataRequestKind, DataRequestStatus


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
