"""The payments module's queries. It never commits: services own the transaction."""

from typing import TYPE_CHECKING

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert

from app.modules.payments.domain.payments import PaymentMode, PaymentPurpose, PaymentStatus
from app.modules.payments.models import Payment, PaymentEvent, ReconciliationIssue, Refund

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.payments.domain.refunds import RefundKind, RefundStatus


class PaymentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def by_public_id(self, public_id: uuid.UUID, *, lock: bool = False) -> Payment | None:
        query = select(Payment).where(Payment.public_id == public_id)
        # A locked read is about the row as it is now: not the copy this session read before the
        # lock, which is what it would otherwise be given back.
        locked = query.with_for_update().execution_options(populate_existing=True)
        return await self._db.scalar(locked if lock else query)

    async def by_id(self, payment_id: int, *, lock: bool = False) -> Payment:
        query = select(Payment).where(Payment.id == payment_id)
        locked = query.with_for_update().execution_options(populate_existing=True)
        return (await self._db.scalars(locked if lock else query)).one()

    async def by_ids(self, payment_ids: Collection[int]) -> dict[int, Payment]:
        if not payment_ids:
            return {}
        rows = await self._db.scalars(select(Payment).where(Payment.id.in_(payment_ids)))
        return {row.id: row for row in rows}

    async def by_provider_payment(self, provider: str, payment_id: str) -> Payment | None:
        """The payment the gateway knows by this id, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(Payment.provider == provider, Payment.provider_payment_id == payment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def captured_token_of(self, booking_id: int) -> Payment | None:
        """The booking's token that came in, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(
                Payment.booking_id == booking_id,
                Payment.purpose == PaymentPurpose.TOKEN,
                Payment.status == PaymentStatus.CAPTURED,
            )
            .order_by(Payment.id.desc())
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def by_order(self, provider: str, order_id: str) -> Payment | None:
        """The payment for this order at this gateway, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(Payment.provider == provider, Payment.provider_order_id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    # Mandates (step 6.7).

    async def by_debit_order(self, provider: str, order_id: str) -> Payment | None:
        """The mandate payment this debit order belongs to, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(Payment.provider == provider, Payment.provider_debit_order_id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def by_mandate(self, provider: str, mandate_id: str) -> Payment | None:
        """The payment a mandate blocks the token of, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(Payment.provider == provider, Payment.provider_mandate_id == mandate_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def mandate_of(self, booking_id: int) -> Payment | None:
        """The booking's token taken by mandate, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(
                Payment.booking_id == booking_id,
                Payment.purpose == PaymentPurpose.TOKEN,
                Payment.mode == PaymentMode.UPI_MANDATE,
            )
            .order_by(Payment.id.desc())
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def debits_waiting(self, *, sent_before: datetime, limit: int) -> list[Payment]:
        """Mandate debits sent and not yet come back, the oldest first."""
        rows = await self._db.scalars(
            select(Payment)
            .where(
                Payment.mode == PaymentMode.UPI_MANDATE,
                Payment.status == PaymentStatus.BLOCKED,
                Payment.provider_debit_order_id.is_not(None),
                Payment.debit_after <= sent_before,
            )
            .order_by(Payment.debit_after)
            .limit(limit)
        )
        return list(rows)

    async def by_key(self, key: str) -> Payment | None:
        return await self._db.scalar(select(Payment).where(Payment.idempotency_key == key))

    async def add_once(
        self,
        *,
        booking_id: int,
        purpose: str,
        mode: str,
        provider: str,
        key: str,
        amount_paise: int,
        made_at: datetime,
        invoice_id: int | None = None,
        mandate_expires_at: datetime | None = None,
    ) -> Payment:
        """The payment with this key, added if there isn't one yet. Two requests at once get the
        same row."""
        await self._db.execute(
            insert(Payment)
            .values(
                booking_id=booking_id,
                purpose=purpose,
                mode=mode,
                provider=provider,
                idempotency_key=key,
                amount_paise=amount_paise,
                made_at=made_at,
                invoice_id=invoice_id,
                mandate_expires_at=mandate_expires_at,
            )
            .on_conflict_do_nothing(index_elements=[Payment.idempotency_key])
        )
        found = await self.by_key(key)
        assert found is not None  # noqa: S101 - just added, or there already
        return found

    async def set_order_once(self, public_id: uuid.UUID, order_id: str) -> bool:
        """Keeps the first order given to this payment, should two requests ask at once: whether
        this was it."""
        changed = await self._db.scalar(
            update(Payment)
            .where(Payment.public_id == public_id, Payment.provider_order_id.is_(None))
            .values(provider_order_id=order_id)
            .returning(Payment.id)
        )
        return changed is not None

    async def set_customer_once(self, public_id: uuid.UUID, customer_id: str) -> None:
        """A mandate's customer at the gateway, kept the first time it's given."""
        await self._db.execute(
            update(Payment)
            .where(Payment.public_id == public_id, Payment.provider_customer_id.is_(None))
            .values(provider_customer_id=customer_id)
        )

    async def order_id_of(self, public_id: uuid.UUID) -> str | None:
        """The order as saved now, whatever this session read earlier."""
        return await self._db.scalar(
            select(Payment.provider_order_id).where(Payment.public_id == public_id)
        )

    async def of_bookings(
        self, booking_ids: Collection[int], *, purpose: PaymentPurpose | None = None
    ) -> list[Payment]:
        if not booking_ids:
            return []
        query = select(Payment).where(Payment.booking_id.in_(booking_ids))
        if purpose is not None:
            query = query.where(Payment.purpose == purpose)
        rows = await self._db.scalars(query.order_by(Payment.id))
        return list(rows)

    # Payment links (step 6.5).

    async def open_link_of(self, invoice_id: int) -> Payment | None:
        """The invoice's payment whose link can still be paid, or is being made."""
        return await self._db.scalar(
            select(Payment).where(Payment.invoice_id == invoice_id, Payment.link_ended_at.is_(None))
        )

    async def ended_links_of(self, invoice_id: int) -> int:
        return int(
            await self._db.scalar(
                select(func.count())
                .select_from(Payment)
                .where(Payment.invoice_id == invoice_id, Payment.link_ended_at.is_not(None))
            )
            or 0
        )

    async def by_link(self, provider: str, link_id: str) -> Payment | None:
        """The payment the gateway's link belongs to, locked, as it is now."""
        return await self._db.scalar(
            select(Payment)
            .where(Payment.provider == provider, Payment.provider_link_id == link_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    # Reconciliation (step 6.6).

    async def waiting_tokens(
        self, *, made_after: datetime, made_before: datetime, limit: int
    ) -> list[Payment]:
        """Tokens whose checkout hasn't come back, oldest first."""
        rows = await self._db.scalars(
            select(Payment)
            .where(
                Payment.purpose == PaymentPurpose.TOKEN,
                Payment.status.in_([PaymentStatus.CREATED, PaymentStatus.AUTHORIZED]),
                Payment.provider_order_id.is_not(None),
                Payment.made_at >= made_after,
                Payment.made_at <= made_before,
            )
            .order_by(Payment.made_at)
            .limit(limit)
        )
        return list(rows)

    async def open_links(self, *, made_after: datetime | None, limit: int) -> list[Payment]:
        """Links not yet paid, ended or refused, oldest first."""
        query = select(Payment).where(
            Payment.purpose == PaymentPurpose.OWNER_INVOICE,
            Payment.status == PaymentStatus.CREATED,
            Payment.provider_link_id.is_not(None),
            Payment.link_ended_at.is_(None),
        )
        if made_after is not None:
            query = query.where(Payment.made_at >= made_after)
        rows = await self._db.scalars(query.order_by(Payment.id).limit(limit))
        return list(rows)

    async def captured_between(
        self,
        *,
        after: datetime,
        before: datetime,
        limit: int,
        past: tuple[datetime, int] | None = None,
    ) -> list[Payment]:
        """Payments captured in ``[after, before)``, oldest first, ``limit`` at a time: the
        next ones from just after ``past``, a payment's capture time and id."""
        query = select(Payment).where(
            Payment.status == PaymentStatus.CAPTURED,
            Payment.captured_at >= after,
            Payment.captured_at < before,
        )
        if past is not None:
            query = query.where(tuple_(Payment.captured_at, Payment.id) > tuple_(*past))
        rows = await self._db.scalars(query.order_by(Payment.captured_at, Payment.id).limit(limit))
        return list(rows)

    async def refunds_waiting(self, *, limit: int) -> list[Refund]:
        """Refunds asked for or sent, and not yet back from the bank, oldest first."""
        rows = await self._db.scalars(
            select(Refund)
            .where(Refund.status.in_(["requested", "pending"]))
            .order_by(Refund.requested_at)
            .limit(limit)
        )
        return list(rows)

    async def counts_waiting(self) -> tuple[int, int, int]:
        """How many tokens, links and refunds are waiting on the gateway."""
        tokens = await self._db.scalar(
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.purpose == PaymentPurpose.TOKEN,
                Payment.status == PaymentStatus.AUTHORIZED,
            )
        )
        links = await self._db.scalar(
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.purpose == PaymentPurpose.OWNER_INVOICE,
                Payment.status == PaymentStatus.CREATED,
                Payment.link_ended_at.is_(None),
            )
        )
        refunds = await self._db.scalar(
            select(func.count())
            .select_from(Refund)
            .where(Refund.status.in_(["requested", "pending"]))
        )
        return int(tokens or 0), int(links or 0), int(refunds or 0)

    async def add_issue_once(
        self,
        *,
        kind: str,
        provider: str,
        reference: str,
        booking_code: str | None,
        amount_paise: int | None,
        detail: str,
        found_at: datetime,
    ) -> bool:
        """Whether this raised it: False if it was raised before, open or not."""
        added = await self._db.scalar(
            insert(ReconciliationIssue)
            .values(
                kind=kind,
                provider=provider,
                reference=reference,
                booking_code=booking_code,
                amount_paise=amount_paise,
                detail=detail,
                found_at=found_at,
            )
            .on_conflict_do_nothing(constraint="uq_reconciliation_issues_kind_reference")
            .returning(ReconciliationIssue.id)
        )
        return added is not None

    async def issue_page(
        self, *, open_only: bool, after: uuid.UUID | None, limit: int
    ) -> list[ReconciliationIssue]:
        """Newest first, ``limit + 1`` of them (the extra says there's more)."""
        query = select(ReconciliationIssue)
        if open_only:
            query = query.where(ReconciliationIssue.resolved_at.is_(None))
        if after is not None:
            query = query.where(ReconciliationIssue.public_id < after)
        rows = await self._db.scalars(
            query.order_by(ReconciliationIssue.public_id.desc()).limit(limit + 1)
        )
        return list(rows)

    async def issue(self, public_id: uuid.UUID) -> ReconciliationIssue | None:
        """The issue, locked, as it is now."""
        return await self._db.scalar(
            select(ReconciliationIssue)
            .where(ReconciliationIssue.public_id == public_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def open_issues(self) -> int:
        return int(
            await self._db.scalar(
                select(func.count())
                .select_from(ReconciliationIssue)
                .where(ReconciliationIssue.resolved_at.is_(None))
            )
            or 0
        )

    async def add_event_once(
        self,
        *,
        provider: str,
        event_id: str,
        kind: str,
        payload: dict[str, object],
        received_at: datetime,
    ) -> int | None:
        """The new event's id; None if this event was stored before."""
        return await self._db.scalar(
            insert(PaymentEvent)
            .values(
                provider=provider,
                provider_event_id=event_id,
                event_type=kind,
                payload=payload,
                received_at=received_at,
            )
            .on_conflict_do_nothing(constraint="uq_payment_events_provider_event")
            .returning(PaymentEvent.id)
        )

    async def event(self, event_id: int) -> PaymentEvent | None:
        """The event, locked, as it is now."""
        return await self._db.scalar(
            select(PaymentEvent)
            .where(PaymentEvent.id == event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def add_refund_once(
        self,
        *,
        payment_id: int,
        kind: RefundKind,
        status: RefundStatus,
        amount_paise: int,
        reason: str,
        key: str,
        requested_at: datetime,
        requested_by: int | None,
    ) -> Refund | None:
        """The new refund; None if this key has one already."""
        new = await self._db.scalar(
            insert(Refund)
            .values(
                payment_id=payment_id,
                kind=kind,
                status=status,
                amount_paise=amount_paise,
                reason=reason,
                idempotency_key=key,
                requested_at=requested_at,
                requested_by=requested_by,
            )
            .on_conflict_do_nothing(index_elements=[Refund.idempotency_key])
            .returning(Refund.id)
        )
        if new is None:
            return None
        return await self._db.scalar(select(Refund).where(Refund.id == new))

    async def refund_by_key(self, key: str) -> Refund | None:
        """The refund with this key, locked, as it is now."""
        return await self._db.scalar(
            select(Refund)
            .where(Refund.idempotency_key == key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def refund_by_public_id(
        self, public_id: uuid.UUID, *, lock: bool = False
    ) -> Refund | None:
        query = select(Refund).where(Refund.public_id == public_id)
        locked = query.with_for_update().execution_options(populate_existing=True)
        return await self._db.scalar(locked if lock else query)

    async def refund_by_provider_id(self, provider_refund_id: str) -> Refund | None:
        """The refund the gateway knows by this id, locked, as it is now."""
        return await self._db.scalar(
            select(Refund)
            .where(Refund.provider_refund_id == provider_refund_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def refunds_of(self, payment_ids: Collection[int]) -> dict[int, list[Refund]]:
        """Each payment's refunds, oldest first; a payment with none is left out."""
        if not payment_ids:
            return {}
        rows = await self._db.scalars(
            select(Refund)
            .where(Refund.payment_id.in_(payment_ids))
            .order_by(Refund.id)
            .execution_options(populate_existing=True)
        )
        found: dict[int, list[Refund]] = {}
        for row in rows:
            found.setdefault(row.payment_id, []).append(row)
        return found

    async def refund_page(
        self, *, status: RefundStatus | None, after: uuid.UUID | None, limit: int
    ) -> list[Refund]:
        """Refunds oldest first, of one status if asked, ``limit + 1`` of them (the extra says
        there's more): a queue, worked from its front."""
        query = select(Refund)
        if status is not None:
            query = query.where(Refund.status == status)
        if after is not None:
            query = query.where(Refund.public_id > after)
        rows = await self._db.scalars(query.order_by(Refund.public_id).limit(limit + 1))
        return list(rows)
