"""The payments module's part of a person's data export (DPDP; ADR 0018): what they paid, for
which booking, and how far it got."""

from typing import TYPE_CHECKING

from app.modules.booking.service import booking_codes_of
from app.modules.payments.repository import PaymentRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def payments_part(db: AsyncSession, user_id: int) -> dict[str, object]:
    codes = await booking_codes_of(db, user_id)
    payments = await PaymentRepository(db).of_bookings(codes.keys())
    if not payments:
        return {}
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
            }
            for payment in payments
        ]
    }
