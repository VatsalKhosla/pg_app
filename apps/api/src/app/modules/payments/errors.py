"""The payments module's errors (ARCHITECTURE §15)."""

from app.core.errors import AppError, ServiceUnavailableError


class PaymentGatewayUnavailableError(ServiceUnavailableError):
    """The gateway can't be reached, or said something it shouldn't."""

    code = "PAYMENT_GATEWAY_UNAVAILABLE"
    title = "Payments can't be reached right now"


class PaymentGatewayRefusedError(AppError):
    """The gateway understood and said no: trying the same again won't help. Only jobs meet this,
    and they record why."""

    status = 502
    code = "PAYMENT_GATEWAY_REFUSED"
    title = "The payment gateway refused that"


class RefundTooMuchError(AppError):
    """More than what's left of the payment."""

    status = 409
    code = "REFUND_TOO_MUCH"
    title = "That's more than can go back"


class RefundNeedsSecondPersonError(AppError):
    """The person who asked for a refund can't approve it too."""

    status = 409
    code = "REFUND_NEEDS_SECOND_PERSON"
    title = "Someone else has to approve this refund"


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
