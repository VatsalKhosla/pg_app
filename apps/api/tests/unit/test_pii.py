import pytest

from app.core.pii import mask_pii, mask_text


@pytest.mark.parametrize(
    "phone",
    [
        "+919876543210",
        "+91 98765 43210",
        "+91-98765-43210",
        "919876543210",
        "9876543210",
        "98765 43210",
        "09876543210",
        "+14155550123",
    ],
)
def test_masks_phone_numbers_to_their_last_four_digits(phone: str) -> None:
    masked = mask_text(f"OTP sent to {phone} just now")

    assert masked == f"OTP sent to ******{phone[-4:]} just now"


@pytest.mark.parametrize(
    "text",
    [
        "BK-7F3K2Q9M",  # booking code
        "0192f6d4-8e1c-7c3a-9b1e-2f4a6c8e0b1d",  # UUID
        "2026-10-18T14:12:56Z",  # timestamp
        "1234567890",  # ten digits, but not an Indian mobile number
        "300000",  # an amount in paise
        "12345678901234",  # a longer number
    ],
)
def test_leaves_other_numbers_alone(text: str) -> None:
    assert mask_text(text) == text


def test_masks_inside_nested_structures_without_touching_other_values() -> None:
    event = {"user": {"phone": "+919876543210"}, "tags": ["9876543210", 7], "pair": ("x", None)}

    assert mask_pii(event) == {
        "user": {"phone": "******3210"},
        "tags": ["******3210", 7],
        "pair": ("x", None),
    }
