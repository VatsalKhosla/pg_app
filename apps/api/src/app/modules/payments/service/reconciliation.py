"""Reconciliation (ARCHITECTURE §9.6; step 6.6, ADR 0062).

- **Every 15 minutes** (CHECK_STUCK): a token checkout that never came back, a link not yet paid
  and a refund still on its way are asked about at the gateway, and its answer goes through the
  same path a webhook's would. A payment the bank said yes to and nobody captured, or a refund that
  hangs, becomes an issue.
- **Daily** (MATCH_SETTLEMENTS): the last three days' settlement reports, line by line. What the
  gateway kept as its fee, paid our bank and took back for refunds is posted, once each; any line
  that doesn't match what we hold, and any captured payment a week old that no report has settled,
  becomes an issue. Every link still open is asked about too.

An issue is raised once, logged as an error so it alerts, and shown to ops until they close it
with what they did.
"""

from datetime import timedelta
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.core import audit
from app.core.calendar import india_date
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.pagination import split_page
from app.modules.booking.service import BookingTokens
from app.modules.identity.service import Accounts
from app.modules.ledger.domain.ledger import gateway_fee, refund_settled, settled
from app.modules.ledger.service import Ledger
from app.modules.payments.domain.links import LinkStatus
from app.modules.payments.domain.payments import GatewayStatus, PaymentStatus
from app.modules.payments.domain.reconciliation import (
    AUTHORIZED_TOO_LONG,
    CHECKS_PER_RUN,
    GIVE_UP_AFTER,
    REFUND_TOO_LONG,
    STUCK_AFTER,
    UNSETTLED_TOO_LONG,
    IssueKind,
    ItemKind,
    Ours,
    SettlementItem,
    read_item,
)
from app.modules.payments.domain.refunds import RefundStatus
from app.modules.payments.errors import PaymentGatewayUnavailableError
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import IssueView, ReconciliationSummary
from app.modules.payments.service.invoice_links import InvoiceLinks
from app.modules.payments.service.refunds import Refunds
from app.modules.payments.service.settlement import PaymentSettlements

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.pagination import PageRequest
    from app.modules.ledger.domain.ledger import Posting
    from app.modules.payments.domain.payments import GatewayPayment
    from app.modules.payments.models import Payment, ReconciliationIssue
    from app.modules.payments.ports import PaymentGateway

CHECK_STUCK: Final = "payments.check_stuck"
MATCH_SETTLEMENTS: Final = "payments.match_settlements"
# The days of reports each daily run reads: settlements come two working days on, and reading
# again is harmless.
REPORT_DAYS: Final = (1, 2, 3)
# A captured payment is looked for in reports for this long after it should have settled.
UNSETTLED_WINDOW: Final = timedelta(days=30)
DAILY_LIMIT: Final = 500
# A refund asked for and not sent this long after.
UNSENT_TOO_LONG: Final = timedelta(hours=1)

logger = structlog.stdlib.get_logger(__name__)

_issues = metrics.get_meter("app.payments").create_counter(
    "payments.reconciliation_issues", description="What reconciliation found, by kind"
)


def _best(attempts: Sequence[GatewayPayment]) -> GatewayPayment | None:
    """The attempt that says most: one captured, else one the bank said yes to."""
    for wanted in (GatewayStatus.CAPTURED, GatewayStatus.AUTHORIZED):
        for attempt in attempts:
            if attempt.status is wanted:
                return attempt
    return None


class Reconciliation:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._payments = PaymentRepository(db)
        self._settlements = PaymentSettlements(db, clock)
        self._refunds = Refunds(db, clock)
        self._links = InvoiceLinks(db, clock)
        self._ledger = Ledger(db, clock)
        self._tokens = BookingTokens(db, clock)
        self._accounts = Accounts(db)

    async def check_stuck(self, gateway: PaymentGateway) -> None:
        """The 15-minute job. A gateway out of reach ends this run; the next one tries again."""
        now = self._clock.now()
        try:
            await self._waiting_tokens(gateway)
            await self._open_links(gateway, made_after=now - GIVE_UP_AFTER, limit=CHECKS_PER_RUN)
            await self._waiting_refunds(gateway)
        except PaymentGatewayUnavailableError:
            logger.warning("reconciliation couldn't reach the gateway: it tries again next time")

    async def match_settlements(self, gateway: PaymentGateway) -> None:
        """The daily job."""
        today = india_date(self._clock.now())
        try:
            for days in REPORT_DAYS:
                for item in await gateway.settlement_items(today - timedelta(days=days)):
                    await self._match(gateway.name, item)
            if gateway.settles:
                await self._unsettled(gateway.name)
            await self._open_links(gateway, made_after=None, limit=DAILY_LIMIT)
        except PaymentGatewayUnavailableError:
            logger.warning("reconciliation couldn't reach the gateway: it tries again tomorrow")

    async def summary(self) -> ReconciliationSummary:
        async with self._db.begin():
            tokens, links, refunds = await self._payments.counts_waiting()
            open_issues = await self._payments.open_issues()
        return ReconciliationSummary(
            open_issues=open_issues,
            tokens_authorized=tokens,
            links_open=links,
            refunds_waiting=refunds,
        )

    async def issues(
        self, request: PageRequest, *, open_only: bool
    ) -> tuple[list[IssueView], uuid.UUID | None]:
        async with self._db.begin():
            found = await self._payments.issue_page(
                open_only=open_only, after=request.after, limit=request.limit
            )
            items, next_cursor = split_page(found, request, cursor_of=lambda row: row.public_id)
            people = await self._accounts.many(
                {row.resolved_by for row in items if row.resolved_by is not None}
            )
        names = {person: account.name for person, account in people.items()}
        return [_issue_view(row, names) for row in items], next_cursor

    async def resolve(self, actor: Actor, issue_id: uuid.UUID, *, resolution: str) -> IssueView:
        """Ops close an issue with what they did. 409 INVALID_TRANSITION if it's closed already."""
        async with self._db.begin():
            issue = await self._payments.issue(issue_id)
            if issue is None:
                raise NotFoundError
            if issue.resolved_at is not None:
                raise InvalidTransitionError("This issue is closed already.")
            issue.resolved_at = self._clock.now()
            issue.resolved_by = actor.user_id
            issue.resolution = resolution.strip()
            await audit.record(
                self._db,
                clock=self._clock,
                actor=audit.Actor("staff", actor.user_id),
                action="reconciliation.resolved",
                entity_type="reconciliation_issue",
                entity_id=str(issue.public_id),
                details={"kind": issue.kind, "note": issue.resolution},
            )
            account = (await self._accounts.many([actor.user_id]))[actor.user_id]
        return _issue_view(issue, {actor.user_id: account.name})

    async def _waiting_tokens(self, gateway: PaymentGateway) -> None:
        now = self._clock.now()
        for payment in await self._payments.waiting_tokens(
            made_after=now - GIVE_UP_AFTER, made_before=now - STUCK_AFTER, limit=CHECKS_PER_RUN
        ):
            if payment.provider != gateway.name or payment.provider_order_id is None:
                continue
            found = _best(await gateway.order_payments(payment.provider_order_id))
            if found is None:
                continue
            locked = await self._payments.by_id(payment.id, lock=True)
            await self._settlements.apply(locked, found, by=audit.SYSTEM)
            made_at = locked.made_at or now
            if locked.status == PaymentStatus.AUTHORIZED and now - made_at > AUTHORIZED_TOO_LONG:
                await self._raise(
                    IssueKind.STUCK_AUTHORIZED,
                    gateway.name,
                    found.id,
                    payment=locked,
                    amount_paise=found.amount_paise,
                    detail="The bank said yes, but the payment hasn't been captured: the gateway "
                    "refunds it by itself in 5 days unless someone captures it.",
                )

    async def _open_links(
        self, gateway: PaymentGateway, *, made_after: datetime | None, limit: int
    ) -> None:
        for payment in await self._payments.open_links(made_after=made_after, limit=limit):
            if payment.provider != gateway.name or payment.provider_link_id is None:
                continue
            link = await gateway.fetch_payment_link(payment.provider_link_id)
            found = None
            if link.status is LinkStatus.PAID and link.payment_id is not None:
                found = await gateway.fetch_payment(link.payment_id)
            await self._links.settle(gateway.name, link, found)

    async def _waiting_refunds(self, gateway: PaymentGateway) -> None:
        now = self._clock.now()
        for refund in await self._payments.refunds_waiting(limit=CHECKS_PER_RUN):
            payment = await self._payments.by_id(refund.payment_id)
            if refund.status == RefundStatus.REQUESTED:
                if now - refund.requested_at > UNSENT_TOO_LONG:
                    await self._raise(
                        IssueKind.REFUND_STUCK,
                        payment.provider,
                        str(refund.public_id),
                        payment=payment,
                        amount_paise=refund.amount_paise,
                        detail="Asked for over an hour ago and not yet taken by the gateway.",
                    )
                continue
            if (
                payment.provider != gateway.name
                or payment.provider_payment_id is None
                or refund.provider_refund_id is None
            ):
                continue
            for found in await gateway.payment_refunds(payment.provider_payment_id):
                if found.id == refund.provider_refund_id:
                    await self._refunds.settle(gateway.name, found, None)
            if (
                refund.status == RefundStatus.PENDING
                and now - refund.requested_at > REFUND_TOO_LONG
            ):
                await self._raise(
                    IssueKind.REFUND_STUCK,
                    gateway.name,
                    refund.provider_refund_id,
                    payment=payment,
                    amount_paise=refund.amount_paise,
                    detail="The gateway has had this refund for a week and not sent it.",
                )

    async def _match(self, provider: str, item: SettlementItem) -> None:
        payment: Payment | None = None
        ours: Ours | None = None
        if item.kind == ItemKind.PAYMENT:
            payment = await self._payments.by_provider_payment(provider, item.entity_id)
            if payment is not None:
                ours = Ours(payment.amount_paise, done=payment.status == PaymentStatus.CAPTURED)
        elif item.kind == ItemKind.REFUND:
            refund = await self._payments.refund_by_provider_id(item.entity_id)
            if refund is not None:
                payment = await self._payments.by_id(refund.payment_id)
                ours = Ours(refund.amount_paise, done=refund.status == RefundStatus.PROCESSED)
        reading = read_item(item, ours)
        if reading.issue is not None:
            await self._raise(
                reading.issue,
                provider,
                item.entity_id,
                payment=payment,
                amount_paise=item.amount_paise,
                detail=f"The settlement report's {item.kind} line doesn't match what we hold.",
            )
            return
        assert payment is not None  # noqa: S101 - read_item matched it to ours
        postings: list[tuple[str, Posting]] = []
        if reading.fee_paise > 0:
            postings.append((f"gateway_fee:{item.entity_id}", gateway_fee(reading.fee_paise)))
        if reading.settled_paise > 0:
            postings.append((f"settled:{item.entity_id}", settled(reading.settled_paise)))
        if reading.refund_paise > 0:
            postings.append(
                (f"refund_settled:{item.entity_id}", refund_settled(reading.refund_paise))
            )
        code = await self._tokens.code_of(payment.booking_id)
        for key, posting in postings:
            await self._ledger.post(
                posting,
                key=key,
                booking_id=payment.booking_id,
                booking_code=code,
                payment_id=payment.id,
                memo=item.settlement_id or "",
            )

    async def _unsettled(self, provider: str) -> None:
        now = self._clock.now()
        due_by = now - UNSETTLED_TOO_LONG
        captured = [
            payment
            for payment in await self._payments.captured_between(
                after=due_by - UNSETTLED_WINDOW, before=due_by, limit=DAILY_LIMIT
            )
            if payment.provider == provider and payment.provider_payment_id is not None
        ]
        posted = await self._ledger.posted(
            {f"settled:{payment.provider_payment_id}" for payment in captured}
        )
        for payment in captured:
            if f"settled:{payment.provider_payment_id}" not in posted:
                await self._raise(
                    IssueKind.NOT_SETTLED,
                    provider,
                    str(payment.provider_payment_id),
                    payment=payment,
                    amount_paise=payment.amount_paise,
                    detail="Captured a week ago or more, and no settlement report has paid it.",
                )

    async def _raise(
        self,
        kind: IssueKind,
        provider: str,
        reference: str,
        *,
        payment: Payment | None,
        amount_paise: int | None,
        detail: str,
    ) -> None:
        code = None if payment is None else await self._tokens.code_of(payment.booking_id)
        if await self._payments.add_issue_once(
            kind=kind,
            provider=provider,
            reference=reference,
            booking_code=code,
            amount_paise=amount_paise,
            detail=detail,
            found_at=self._clock.now(),
        ):
            logger.error("reconciliation found something to look at", kind=kind, booking=code)
            _issues.add(1, {"kind": kind})


def _issue_view(row: ReconciliationIssue, names: dict[int, str | None]) -> IssueView:
    return IssueView(
        id=row.public_id,
        kind=IssueKind(row.kind),
        provider=row.provider,
        reference=row.reference,
        booking=row.booking_code,
        amount_paise=row.amount_paise,
        detail=row.detail,
        found_at=row.found_at,
        resolved_at=row.resolved_at,
        resolved_by=None if row.resolved_by is None else names.get(row.resolved_by),
        resolution=row.resolution,
    )
