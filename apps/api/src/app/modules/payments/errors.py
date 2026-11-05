"""The payments module's errors (ARCHITECTURE §15)."""

from app.core.errors import AppError, ServiceUnavailableError


class PaymentGatewayUnavailableError(ServiceUnavailableError):
    """The gateway can't be reached, or said something it shouldn't."""

    code = "PAYMENT_GATEWAY_UNAVAILABLE"
    title = "Payments can't be reached right now"


class PaymentSignatureInvalidError(AppError):
    """What came back from checkout isn't what the gateway signed: nothing moves."""

    status = 400
    code = "PAYMENT_SIGNATURE_INVALID"
    title = "That payment couldn't be verified"


class WebhookInvalidError(AppError):
    """Not signed by the gateway, not an event, or far too old to be anything but a replay."""

    status = 400
    code = "WEBHOOK_INVALID"
    title = "That webhook was refused"


class PaymentMismatchError(AppError):
    """The gateway's payment isn't this order's, or isn't its amount: nothing moves, and it's
    logged for someone to look at."""

    status = 409
    code = "PAYMENT_MISMATCH"
    title = "That payment doesn't match this booking"
