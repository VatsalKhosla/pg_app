"""What the gateway's word about a payment comes to (steps 6.1 and 6.2, ADRs 0056 and 0057), from a
checkout or a webhook, inside the caller's transaction, with the payment's row locked.

Anything can come twice or out of order: a payment only moves forward, and captured money moves its
booking once. The checks are the same whichever way the word arrived.
"""

from typing import TYPE_CHECKING

import structlog

from app.core import audit
from app.modules.booking.service import BookingTokens, TokenTaken
from app.modules.payments.domain.payments import (
    GatewayStatus,
    PaymentStatus,
    Reading,
    Settlement,
    advanced,
    read_payment,
)
from app.modules.payments.service.refunds import Refunds

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.payments.domain.payments import GatewayPayment
    from app.modules.payments.models import Payment

logger = structlog.stdlib.get_logger(__name__)


class PaymentSettlements:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._tokens = BookingTokens(db, clock)
        self._refunds = Refunds(db, clock)

    async def apply(
        self, payment: Payment, found: GatewayPayment, *, by: audit.Actor
    ) -> Settlement:
        """``payment`` has to be locked, and as it is now."""
        code = await self._tokens.code_of(payment.booking_id)
        reading = read_payment(
            found, order_id=payment.provider_order_id or "", amount_paise=payment.amount_paise
        )
        match reading:
            case Reading.MISMATCH:
                logger.error("a gateway's payment doesn't match its order", booking=code)
                await self._record(payment, "payment.mismatch", code, by=by)
                return Settlement.MISMATCH
            case Reading.PAID:
                return await self._paid(payment, found, code, by=by)
            case Reading.WAITING:
                if found.status is GatewayStatus.AUTHORIZED:
                    payment.provider_payment_id = payment.provider_payment_id or found.id
                    payment.status = advanced(PaymentStatus(payment.status), found.status)
                return Settlement.WAITING
            case Reading.NOT_PAID:
                return Settlement.NOT_PAID

    async def _paid(
        self, payment: Payment, found: GatewayPayment, code: str, *, by: audit.Actor
    ) -> Settlement:
        """The money is in. A payment already captured moves nothing a second time, and comes to
        the same as the first time."""
        if payment.status == PaymentStatus.CAPTURED:
            took_it = await self._tokens.took_token(payment.booking_id)
            return Settlement.PAID if took_it else Settlement.LATE
        payment.status = advanced(PaymentStatus(payment.status), found.status)
        payment.provider_payment_id = found.id
        payment.captured_at = self._clock.now()
        await self._record(payment, "payment.captured", code, by=by)
        taken = await self._tokens.take(payment.booking_id, paid_paise=found.amount_paise)
        if taken in {TokenTaken.SECURED, TokenTaken.REVIVED}:
            return Settlement.PAID
        logger.warning(
            "a token came in too late to secure its booking", booking=code, came_to=taken
        )
        await self._record(payment, "payment.late", code, by=by, came_to=taken)
        if taken is TokenTaken.MOVED_ON:
            # No booking event carries this one back, so it goes back from here. A refund from the
            # hold's end came with its own event, whose job finds this payment.
            await self._refunds.automatic(
                payment, amount_paise=payment.amount_paise, reason="moved_on"
            )
        return Settlement.LATE

    async def _record(
        self,
        payment: Payment,
        action: str,
        code: str,
        *,
        by: audit.Actor,
        came_to: TokenTaken | None = None,
    ) -> None:
        details: dict[str, object] = {"booking": code, "amountPaise": payment.amount_paise}
        if came_to is not None:
            details["cameTo"] = came_to
        await audit.record(
            self._db,
            clock=self._clock,
            actor=by,
            action=action,
            entity_type="payment",
            entity_id=str(payment.public_id),
            details=details,
        )
