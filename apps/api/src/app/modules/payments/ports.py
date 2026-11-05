"""What the payments module needs from a gateway (ARCHITECTURE §9.1). UPI mandates join this in
step 6.7 and split settlement in Phase 9, each as its step builds it."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.payments.domain.payments import GatewayOrder, GatewayPayment, Provider
    from app.modules.payments.domain.refunds import GatewayRefund
    from app.modules.payments.domain.webhooks import GatewayEvent


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

    def read_webhook(self, raw_body: bytes) -> GatewayEvent | None:
        """A verified webhook's event, whatever kind it is; None if it isn't one at all."""
        ...

    async def fetch_payment(self, payment_id: str) -> GatewayPayment:
        """The payment as the gateway has it now."""
        ...

    async def refund(
        self, *, payment_id: str, amount_paise: int, receipt: str, notes: Mapping[str, str]
    ) -> GatewayRefund:
        """``amount_paise`` of the payment goes back. ``receipt`` is unique to the refund: asking
        again, after an answer that got lost, gives back the same refund. Raises
        PaymentGatewayRefusedError when the gateway says no, which asking again won't change."""
        ...
