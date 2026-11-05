"""What a payment means, whichever gateway took it (step 6.1, ADR 0056)."""

import pytest

from app.modules.payments.domain.payments import (
    INR,
    GatewayPayment,
    GatewayStatus,
    PaymentStatus,
    Reading,
    advanced,
    read_payment,
    token_key,
    token_receipt,
)
from app.modules.payments.domain.signatures import checkout_signature, same, webhook_signature

ORDER = "order_IluGWxBm9U8zJ8"
TOKEN = 200_000


def _found(
    status: GatewayStatus = GatewayStatus.CAPTURED,
    *,
    order: str | None = ORDER,
    amount: int = TOKEN,
    currency: str = INR,
) -> GatewayPayment:
    return GatewayPayment("pay_DG4ZdRK8ZnXC3k", order, amount, currency, status)


@pytest.mark.parametrize(
    ("status", "reading"),
    [
        (GatewayStatus.CAPTURED, Reading.PAID),
        (GatewayStatus.CREATED, Reading.WAITING),
        (GatewayStatus.AUTHORIZED, Reading.WAITING),
        (GatewayStatus.REFUNDED, Reading.NOT_PAID),
        (GatewayStatus.FAILED, Reading.NOT_PAID),
    ],
)
def test_only_money_in_is_paid(status: GatewayStatus, reading: Reading) -> None:
    assert read_payment(_found(status), order_id=ORDER, amount_paise=TOKEN) is reading


@pytest.mark.parametrize(
    "found",
    [
        _found(order="order_someone_elses"),
        _found(order=None),
        _found(amount=TOKEN - 1),
        _found(amount=TOKEN + 1),
        _found(currency="USD"),
    ],
)
def test_a_payment_that_isnt_this_orders_exact_token_moves_nothing(found: GatewayPayment) -> None:
    assert read_payment(found, order_id=ORDER, amount_paise=TOKEN) is Reading.MISMATCH


@pytest.mark.parametrize(
    ("status", "seen", "after"),
    [
        (PaymentStatus.CREATED, GatewayStatus.CREATED, PaymentStatus.CREATED),
        (PaymentStatus.CREATED, GatewayStatus.AUTHORIZED, PaymentStatus.AUTHORIZED),
        (PaymentStatus.CREATED, GatewayStatus.CAPTURED, PaymentStatus.CAPTURED),
        (PaymentStatus.CREATED, GatewayStatus.FAILED, PaymentStatus.CREATED),
        (PaymentStatus.AUTHORIZED, GatewayStatus.CREATED, PaymentStatus.AUTHORIZED),
        (PaymentStatus.AUTHORIZED, GatewayStatus.AUTHORIZED, PaymentStatus.AUTHORIZED),
        (PaymentStatus.AUTHORIZED, GatewayStatus.CAPTURED, PaymentStatus.CAPTURED),
        (PaymentStatus.AUTHORIZED, GatewayStatus.FAILED, PaymentStatus.AUTHORIZED),
        (PaymentStatus.CAPTURED, GatewayStatus.CREATED, PaymentStatus.CAPTURED),
        (PaymentStatus.CAPTURED, GatewayStatus.AUTHORIZED, PaymentStatus.CAPTURED),
        (PaymentStatus.CAPTURED, GatewayStatus.CAPTURED, PaymentStatus.CAPTURED),
        (PaymentStatus.CAPTURED, GatewayStatus.REFUNDED, PaymentStatus.CAPTURED),
    ],
)
def test_a_payment_only_moves_forward(
    status: PaymentStatus, seen: GatewayStatus, after: PaymentStatus
) -> None:
    assert advanced(status, seen) is after


def test_a_booking_has_one_order_at_each_gateway_with_a_receipt_razorpay_takes() -> None:
    assert token_key("razorpay", "BK-7F3K2Q9M") == "token:razorpay:BK-7F3K2Q9M"
    assert token_key("fake", "BK-7F3K2Q9M") != token_key("razorpay", "BK-7F3K2Q9M")
    receipt = token_receipt("BK-7F3K2Q9M")
    assert receipt == "token-BK-7F3K2Q9M"
    assert len(receipt) <= 40
    assert receipt.isascii()


def test_signatures_match_the_published_hmac() -> None:
    # Worked out separately: printf 'order_1|pay_1' | openssl dgst -sha256 -hmac secret
    assert checkout_signature("secret", order_id="order_1", payment_id="pay_1") == (
        "52115a0d3400de9e86aade1f1b6eba9e8974604f4e267a9e9a16633a4c8dd2cb"
    )
    # printf '{"a":1}' | openssl dgst -sha256 -hmac secret
    assert (
        webhook_signature("secret", b'{"a":1}')
        == "aa9e2e3575f5d7098b6caccd790888c36d5fdb63342a73bada2d6a51747a8494"
    )


def test_comparing_signatures_copes_with_anything() -> None:
    assert same("abc", "abc")
    assert not same("abc", "abd")
    assert not same("abc", "")
    assert not same("abc", "résumé")
