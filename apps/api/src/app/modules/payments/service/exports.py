"""The payments module's part of a person's data export (DPDP; ADR 0018): what they paid, for
which booking, and how far it got."""

from typing import TYPE_CHECKING

from app.modules.booking.service import booking_codes_of
from app.modules.payments.domain.payments import PaymentPurpose
from app.modules.payments.repository import PaymentRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def payments_part(db: AsyncSession, user_id: int) -> dict[str, object]:
    codes = await booking_codes_of(db, user_id)
    repository = PaymentRepository(db)
    # A student's own: an owner's invoice is the owner's (step 6.5).
    payments = await repository.of_bookings(codes.keys(), purpose=PaymentPurpose.TOKEN)
    if not payments:
        return {}
    refunds = await repository.refunds_of([payment.id for payment in payments])
    return {
        "payments": [
            {
                "booking": codes[payment.booking_id],
                "purpose": payment.purpose,
                "amountPaise": payment.amount_paise,
                "status": payment.status,
                "gateway": payment.provider,
                "gatewayPaymentId": payment.provider_payment_id,
                "madeAt": payment.created_at.isoformat(),
                "capturedAt": None
                if payment.captured_at is None
                else payment.captured_at.isoformat(),
                "refunds": [
                    {
                        "amountPaise": refund.amount_paise,
                        "status": refund.status,
                        "reference": refund.reference,
                        "requestedAt": refund.requested_at.isoformat(),
                        "processedAt": None
                        if refund.processed_at is None
                        else refund.processed_at.isoformat(),
                    }
                    for refund in refunds.get(payment.id, [])
                ],
            }
            for payment in payments
        ]
    }
