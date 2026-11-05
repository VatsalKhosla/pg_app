"""Which gateway a process talks to, from its settings (ADR 0056)."""

from typing import TYPE_CHECKING

from app.modules.payments.adapters.fake import FakeGateway
from app.modules.payments.adapters.razorpay import RazorpayGateway

if TYPE_CHECKING:
    import httpx

    from app.config import Settings
    from app.modules.payments.ports import PaymentGateway


def build_gateway(settings: Settings, http: httpx.AsyncClient) -> PaymentGateway:
    if (
        settings.payment_gateway == "fake"
        or settings.razorpay_key_id is None
        or settings.razorpay_key_secret is None
        or settings.razorpay_webhook_secret is None
    ):
        return FakeGateway()
    return RazorpayGateway(
        http,
        key_id=settings.razorpay_key_id,
        key_secret=settings.razorpay_key_secret,
        webhook_secret=settings.razorpay_webhook_secret,
    )
