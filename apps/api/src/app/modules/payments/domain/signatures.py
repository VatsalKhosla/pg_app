"""The two signatures a gateway uses, per Razorpay's docs: HMAC-SHA256 as lowercase hex. Pure."""

import hashlib
import hmac


def checkout_signature(secret: str, *, order_id: str, payment_id: str) -> str:
    """What Checkout hands the browser: over our own order id and the payment's, with the key's
    secret."""
    message = f"{order_id}|{payment_id}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def webhook_signature(secret: str, raw_body: bytes) -> str:
    """The ``X-Razorpay-Signature`` header: over the body exactly as it came, with the webhook's
    own secret."""
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def same(expected: str, given: str) -> bool:
    """In constant time, and false rather than an error for anything odd in ``given``."""
    return hmac.compare_digest(expected.encode(), given.encode())
