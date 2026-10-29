"""Grievances' use cases (PRODUCT_CONTEXT §7; step 3.8, ADR 0034); each method is one transaction.

Anyone may complain and gets a ticket number at once. Signed out, a person gives a name and a phone
number or email address and passes the human check; signed in, their account says who they are,
and its phone is texted when the complaint arrives, is acknowledged and is resolved. A number
someone merely typed is never texted: that would let anyone send our texts to anyone. Ops and
admins (the grievance officer's team) acknowledge each complaint with a reply within 48 hours and
resolve it within a month; both are audited.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

import structlog

from app.config import BRAND_NAME
from app.core import audit
from app.core.calendar import spoken_date
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.human_check import HumanCheckFailedError
from app.core.ids import new_ticket_number, normalize_ticket_number
from app.core.outbox import enqueue
from app.core.pagination import split_page
from app.core.ratelimit import RateLimit, enforce
from app.modules.compliance.domain.grievances import (
    GrievanceStatus,
    acknowledge_by,
    can_move,
    is_late,
    resolve_by,
)
from app.modules.compliance.models import Grievance
from app.modules.compliance.repository import GrievanceRepository
from app.modules.compliance.texts import ACKNOWLEDGED, RECEIVED, RESOLVED
from app.modules.identity.service import Accounts

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.human_check import HumanCheck
    from app.core.pagination import PageRequest
    from app.core.ratelimit import RateLimiter
    from app.modules.compliance.domain.grievances import GrievanceCategory

GRIEVANCE_TEXT: Final = "compliance.grievance_text"
HUMAN_CHECK_ACTION: Final = "grievance"
# A real complaint is rare; a stream of them from one place is someone abusing the form.
PER_IP: Final = RateLimit("grievances-per-ip", limit=5, window=timedelta(hours=1))
PER_USER: Final = RateLimit("grievances-per-user", limit=10, window=timedelta(days=1))
# Ticket numbers are random; a repeat is astronomically rare, but it's checked for.
_TICKET_ATTEMPTS: Final = 5

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Complaint:
    category: GrievanceCategory
    details: str
    reference: str
    name: str | None
    phone_e164: str | None
    email: str | None


@dataclass(frozen=True, slots=True)
class GrievanceView:
    grievance: Grievance
    # The complainant's account, when they were signed in and it still exists.
    account: uuid.UUID | None
    late: bool


class GrievanceService:
    def __init__(
        self, db: AsyncSession, clock: Clock, *, limiter: RateLimiter, human_check: HumanCheck
    ) -> None:
        self._db = db
        self._clock = clock
        self._limiter = limiter
        self._human_check = human_check
        self._grievances = GrievanceRepository(db)
        self._accounts = Accounts(db)

    async def submit(
        self,
        actor: Actor | None,
        complaint: Complaint,
        *,
        human_check_token: str,
        ip_address: str,
    ) -> Grievance:
        if actor is None:
            if not await self._human_check.verify(
                human_check_token, remote_ip=ip_address, action=HUMAN_CHECK_ACTION
            ):
                raise HumanCheckFailedError
            await enforce(self._limiter, PER_IP, ip_address)
        else:
            await enforce(self._limiter, PER_USER, str(actor.user_id))
        now = self._clock.now()
        async with self._db.begin():
            name, phone, email = complaint.name, complaint.phone_e164, complaint.email
            if actor is not None:
                # The account's own phone: the one number known to be theirs.
                account = (await self._accounts.many([actor.user_id]))[actor.user_id]
                name, phone = name or account.name, account.phone_e164
            grievance = Grievance(
                ticket_number=await self._new_ticket_number(),
                user_id=None if actor is None else actor.user_id,
                name=name or "",
                phone_e164=phone,
                email=email,
                category=complaint.category,
                reference=complaint.reference,
                details=complaint.details,
                status=GrievanceStatus.RECEIVED,
                received_at=now,
                acknowledge_by=acknowledge_by(now),
                resolve_by=resolve_by(now),
            )
            self._grievances.add(grievance)
            await self._db.flush()
            await self._text(grievance, RECEIVED)
            logger.info(
                "grievance received",
                ticket=grievance.ticket_number,
                category=complaint.category,
                signed_in=actor is not None,
            )
            return grievance

    async def mine(self, actor: Actor) -> list[Grievance]:
        async with self._db.begin():
            return await self._grievances.of_user(actor.user_id)

    # The grievance officer's team.

    async def page(
        self, page: PageRequest, *, status: GrievanceStatus | None
    ) -> tuple[list[GrievanceView], uuid.UUID | None]:
        async with self._db.begin():
            rows = await self._grievances.page(status=status, after=page.after, limit=page.limit)
            items, next_cursor = split_page(rows, page, cursor_of=lambda row: row.public_id)
            return await self._views(items), next_cursor

    async def get(self, ticket_number: str) -> GrievanceView:
        async with self._db.begin():
            return (await self._views([await self._found(ticket_number)]))[0]

    async def acknowledge(self, actor: Actor, ticket_number: str, *, reply: str) -> GrievanceView:
        async with self._db.begin():
            grievance = await self._found(ticket_number, lock=True)
            self._move(grievance, GrievanceStatus.ACKNOWLEDGED)
            grievance.acknowledged_at, grievance.acknowledged_by = self._clock.now(), actor.user_id
            grievance.reply = reply
            await self._audit(actor, "grievances.acknowledged", grievance)
            await self._text(grievance, ACKNOWLEDGED)
            return (await self._views([grievance]))[0]

    async def resolve(self, actor: Actor, ticket_number: str, *, resolution: str) -> GrievanceView:
        """Resolving one that hasn't been acknowledged acknowledges it too."""
        async with self._db.begin():
            grievance = await self._found(ticket_number, lock=True)
            self._move(grievance, GrievanceStatus.RESOLVED)
            now = self._clock.now()
            if grievance.acknowledged_at is None:
                grievance.acknowledged_at, grievance.acknowledged_by = now, actor.user_id
            grievance.resolved_at, grievance.resolved_by = now, actor.user_id
            grievance.resolution = resolution
            await self._audit(actor, "grievances.resolved", grievance)
            await self._text(grievance, RESOLVED)
            return (await self._views([grievance]))[0]

    async def _found(self, ticket_number: str, *, lock: bool = False) -> Grievance:
        number = normalize_ticket_number(ticket_number)
        grievance = None if number is None else await self._grievances.by_ticket(number, lock=lock)
        if grievance is None:
            raise NotFoundError
        return grievance

    async def _new_ticket_number(self) -> str:
        for _ in range(_TICKET_ATTEMPTS):
            number = new_ticket_number()
            if not await self._grievances.ticket_taken(number):
                return number
        msg = "no free ticket number"
        raise RuntimeError(msg)

    def _move(self, grievance: Grievance, target: GrievanceStatus) -> None:
        if not can_move(GrievanceStatus(grievance.status), target):
            raise InvalidTransitionError(f"A {grievance.status} grievance can't be {target}.")
        grievance.status = target

    async def _text(self, grievance: Grievance, template: str) -> None:
        """A text to a signed-in complainant's phone: one of each kind per grievance, ever."""
        if grievance.user_id is None:
            return
        await enqueue(
            self._db,
            GRIEVANCE_TEXT,
            {"ticket": grievance.ticket_number, "template": template},
            clock=self._clock,
            dedupe_key=f"{GRIEVANCE_TEXT}:{grievance.ticket_number}:{template}",
        )

    async def _audit(self, actor: Actor, action: str, grievance: Grievance) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.Actor("staff" if actor.is_staff else "user", actor.user_id),
            action=action,
            entity_type="grievance",
            entity_id=grievance.ticket_number,
        )

    async def _views(self, grievances: list[Grievance]) -> list[GrievanceView]:
        """The grievances with their complainants' accounts: one query, however many."""
        accounts = await self._accounts.many(
            {grievance.user_id for grievance in grievances if grievance.user_id is not None}
        )
        now = self._clock.now()
        return [
            GrievanceView(
                grievance=grievance,
                account=None
                if (account := accounts.get(grievance.user_id or 0)) is None
                else account.public_id,
                late=is_late(
                    GrievanceStatus(grievance.status), received_at=grievance.received_at, now=now
                ),
            )
            for grievance in grievances
        ]


# The status each text announces: one that has moved on by the time its job runs isn't sent.
_ANNOUNCES: Final = {
    RECEIVED: GrievanceStatus.RECEIVED,
    ACKNOWLEDGED: GrievanceStatus.ACKNOWLEDGED,
    RESOLVED: GrievanceStatus.RESOLVED,
}


class GrievanceTexts:
    """What a queued text says, when the job comes to send it: the ticket and its deadlines;
    nothing once the grievance has moved past what the text says. Inside the job's
    transaction."""

    def __init__(self, db: AsyncSession) -> None:
        self._grievances = GrievanceRepository(db)

    async def message(self, ticket_number: str, template: str) -> tuple[str, dict[str, str]] | None:
        grievance = await self._grievances.by_ticket(ticket_number)
        if grievance is None or grievance.user_id is None or grievance.phone_e164 is None:
            return None
        if grievance.status != _ANNOUNCES[template]:
            return None
        values = {"brand": BRAND_NAME, "ticket": grievance.ticket_number}
        if template in {RECEIVED, ACKNOWLEDGED}:
            values["resolve_by"] = spoken_date(grievance.resolve_by)
        if template == RECEIVED:
            values["acknowledge_by"] = spoken_date(grievance.acknowledge_by)
        return grievance.phone_e164, values


def _moment(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


async def grievances_part(db: AsyncSession, user_id: int) -> dict[str, object]:
    """The grievances' part of a person's data export: the complaints they made signed in, with
    the replies."""
    grievances = await GrievanceRepository(db).of_user(user_id)
    if not grievances:
        return {}
    return {
        "grievances": [
            {
                "ticketNumber": grievance.ticket_number,
                "category": grievance.category,
                "reference": grievance.reference,
                "details": grievance.details,
                "name": grievance.name,
                "email": grievance.email,
                "status": grievance.status,
                "receivedAt": grievance.received_at.isoformat(),
                "acknowledgedAt": _moment(grievance.acknowledged_at),
                "reply": grievance.reply,
                "resolvedAt": _moment(grievance.resolved_at),
                "resolution": grievance.resolution,
            }
            for grievance in grievances
        ]
    }
