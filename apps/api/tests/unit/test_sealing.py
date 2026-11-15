"""Sealed values (app/core/sealing.py, ADR 0070): AES-256-GCM, bound to their context, under keys
that can be rotated."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.sealing import (
    DERIVED_KEY_ID,
    FieldCipher,
    KeyConfigError,
    SealError,
    derived_key,
    new_key,
    parse_keys,
)

SECRET = b"test-only-secret-key-0123456789abcdef"


def _cipher(*ids: str) -> FieldCipher:
    return FieldCipher.from_config(
        ",".join(f"{key_id}:{new_key()}" for key_id in ids), secret_key=SECRET
    )


@given(st.text(max_size=500), st.text(min_size=1, max_size=60))
def test_a_sealed_value_opens_to_what_was_sealed(plain: str, context: str) -> None:
    cipher = FieldCipher.from_config(None, secret_key=SECRET)

    sealed = cipher.seal(plain, context=context)

    assert cipher.open(sealed, context=context) == plain


def test_a_value_never_shows_in_its_sealed_form_and_seals_differently_each_time() -> None:
    cipher = _cipher("k1")

    first = cipher.seal("Asha Verma", context="row:1")
    second = cipher.seal("Asha Verma", context="row:1")

    assert "Asha" not in first
    assert first != second
    assert first.startswith("v1.k1.")


def test_a_value_opens_only_where_it_was_sealed() -> None:
    cipher = _cipher("k1")
    sealed = cipher.seal("Asha Verma", context="tenant_verification:1")

    with pytest.raises(SealError):
        cipher.open(sealed, context="tenant_verification:2")


# Inside the nonce, the ciphertext and the tag. (The very last character of unpadded base64 also
# carries unused bits, so changing it may decode to the same bytes: that's encoding, not data.)
@pytest.mark.parametrize("position", [8, 20, -3])
def test_a_changed_value_doesnt_open(position: int) -> None:
    cipher = _cipher("k1")
    sealed = cipher.seal("Asha Verma", context="row:1")
    flipped = "A" if sealed[position] != "A" else "B"
    at = position % len(sealed)
    changed = sealed[:at] + flipped + sealed[at + 1 :]

    with pytest.raises(SealError):
        cipher.open(changed, context="row:1")


@pytest.mark.parametrize("sealed", ["", "v1", "v1.k1", "v1.k1.", "v2.k1.AAAA", "v1.zz.AAAA", "x"])
def test_anything_but_a_sealed_value_doesnt_open(sealed: str) -> None:
    with pytest.raises(SealError):
        _cipher("k1").open(sealed, context="row:1")


def test_keys_rotate_old_values_still_open_and_new_ones_use_the_first_key() -> None:
    old_key, new = new_key(), new_key()
    before = FieldCipher.from_config(f"k1:{old_key}", secret_key=SECRET)
    after = FieldCipher.from_config(f"k2:{new},k1:{old_key}", secret_key=SECRET)
    sealed_before = before.seal("Asha", context="row:1")

    assert after.open(sealed_before, context="row:1") == "Asha"
    assert after.needs_resealing(sealed_before)
    assert after.seal("Asha", context="row:1").startswith("v1.k2.")
    assert not after.needs_resealing(after.seal("Asha", context="row:1"))
    # A key taken off the list takes its values with it.
    with pytest.raises(SealError):
        FieldCipher.from_config(f"k2:{new}", secret_key=SECRET).open(sealed_before, context="row:1")


def test_without_keys_of_its_own_one_is_derived_from_the_secret_key() -> None:
    cipher = FieldCipher.from_config("", secret_key=SECRET)

    assert cipher.current_key_id == DERIVED_KEY_ID
    assert cipher.keys == ((DERIVED_KEY_ID, derived_key(SECRET)),)
    assert derived_key(SECRET) != derived_key(SECRET + b"x")
    assert len(derived_key(SECRET)) == 32


@pytest.mark.parametrize(
    ("keys", "message"),
    [
        ("k1", "expected id:key"),
        ("K1:" + "A" * 43, "expected id:key"),
        ("k1:not base64!", "base64url"),
        ("k1:" + "A" * 20, "32 bytes"),
        ("k1:" + "A" * 43 + ",k1:" + "A" * 43, "listed twice"),
    ],
)
def test_badly_written_keys_are_refused_without_repeating_them(keys: str, message: str) -> None:
    with pytest.raises(KeyConfigError, match=message) as refused:
        parse_keys(keys)

    assert "A" * 20 not in str(refused.value)


def test_a_new_key_is_32_random_bytes() -> None:
    key = new_key()

    assert parse_keys(f"k1:{key}")[0][1] != parse_keys(f"k1:{new_key()}")[0][1]
    assert len(parse_keys(f"k1:{key}")[0][1]) == 32
