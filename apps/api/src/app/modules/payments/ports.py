"""What the payments module needs from a gateway (ARCHITECTURE §9.1). Refunds join this in step
6.3, UPI mandates in 6.7 and split settlement in Phase 9, each as its step builds it."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.payments.domain.payments import GatewayOrder, GatewayPayment, Provider


class PaymentGateway(Protocol):
    """A payment gateway. Calls that reach it raise PaymentGatewayUnavailableError when it can't
    be reached or says something it shouldn't, so nothing here is ever half-done on our side."""

    # Recorded on each payment.
    name: Provider
    # The public half of the key, which the browser's checkout needs.
    key_id: str

    async def create_order(
        self, *, amount_paise: int, receipt: str, notes: Mapping[str, str]
    ) -> GatewayOrder:
        """The order for exactly ``amount_paise``. ``receipt`` is unique to it: asking again with
        the same one, after an answer that got lost, gives back the same order."""
        ...

    def verify_checkout_signature(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        """Whether ``signature`` is what the gateway gave the browser for this payment on our own
        ``order_id``."""
        ...

    def verify_webhook(self, *, raw_body: bytes, signature: str) -> bool:
        """Whether ``signature`` is the gateway's for this body, exactly as it came."""
        ...

    async def fetch_payment(self, payment_id: str) -> GatewayPayment:
        """The payment as the gateway has it now."""
        ...
