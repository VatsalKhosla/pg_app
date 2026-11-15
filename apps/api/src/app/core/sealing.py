"""Personal data encrypted at rest in the application (ARCHITECTURE §17): sealed values.

Some personal data has to be read back, so it can't be kept as a keyed digest the way sign-in codes
are: a tenant's police-verification details, which their PG's owner prints for the police (ADR
0070). Such values are sealed before they reach the database, with AES-256-GCM, and opened only
where a policy has already said the reader may see them.

- **Bound to their place.** Each value is sealed for a context, such as the row it belongs to, and
  opens only there: a sealed value copied into another row fails to open.
- **Keys can be rotated.** A sealed value names its key. New values use the first key listed, and
  every key listed still opens what it sealed, until the old values have been sealed again.
- **Keys come from FIELD_ENCRYPTION_KEYS**: comma-separated ``id:key`` pairs, each key 32 random
  bytes in base64url. Without it, one key is derived from SECRET_KEY by HKDF, for local
  development, tests and the test site; production refuses that (app/config.py), as rotating
  SECRET_KEY would then make every sealed value unreadable.

Nothing here logs or returns a key, and a value that fails to open says only that it failed.
"""

import base64
import re
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

if TYPE_CHECKING:
    from app.config import Settings

KEY_BYTES: Final = 32
NONCE_BYTES: Final = 12
# The id of the key derived from SECRET_KEY.
DERIVED_KEY_ID: Final = "derived"
_FORMAT: Final = "v1"
_KEY_ID: Final = re.compile(r"[a-z0-9]{1,16}")
_HKDF_INFO: Final = b"pg-platform sealed fields v1"


class SealError(Exception):
    """A sealed value that won't open: changed, sealed for another context, or under a key that
    isn't listed. Deliberately one error for all of these."""


class KeyConfigError(ValueError):
    """FIELD_ENCRYPTION_KEYS isn't a list of ``id:key`` pairs with 32-byte keys."""


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def parse_keys(text: str) -> tuple[tuple[str, bytes], ...]:
    """The keys FIELD_ENCRYPTION_KEYS lists, in order: the first seals new values. The message of
    a KeyConfigError never repeats a key."""
    keys: list[tuple[str, bytes]] = []
    for position, item in enumerate(part.strip() for part in text.split(",")):
        key_id, separator, encoded = item.partition(":")
        if not separator or not _KEY_ID.fullmatch(key_id):
            msg = f"key {position + 1}: expected id:key, the id 1-16 lowercase letters or digits"
            raise KeyConfigError(msg)
        try:
            key = _b64decode(encoded)
        except ValueError:  # binascii.Error is one
            msg = f"key {key_id!r} isn't base64url"
            raise KeyConfigError(msg) from None
        if len(key) != KEY_BYTES:
            msg = f"key {key_id!r} must be {KEY_BYTES} bytes"
            raise KeyConfigError(msg)
        if any(key_id == known for known, _ in keys):
            msg = f"key id {key_id!r} is listed twice"
            raise KeyConfigError(msg)
        keys.append((key_id, key))
    if not keys:
        msg = "no keys listed"
        raise KeyConfigError(msg)
    return tuple(keys)


def derived_key(secret: bytes) -> bytes:
    """The key derived from SECRET_KEY, for environments without FIELD_ENCRYPTION_KEYS."""
    return HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=None, info=_HKDF_INFO).derive(
        secret
    )


def new_key() -> str:
    """A fresh key, as FIELD_ENCRYPTION_KEYS takes it (for an operator making one)."""
    return _b64encode(secrets.token_bytes(KEY_BYTES))


@dataclass(frozen=True, slots=True)
class FieldCipher:
    """Seals and opens values with the listed keys; the first seals."""

    keys: tuple[tuple[str, bytes], ...]

    def __post_init__(self) -> None:
        if not self.keys:
            msg = "a cipher needs at least one key"
            raise KeyConfigError(msg)

    @classmethod
    def from_config(cls, keys: str | None, *, secret_key: bytes) -> FieldCipher:
        """From FIELD_ENCRYPTION_KEYS when set; otherwise the key derived from SECRET_KEY."""
        if keys is None or not keys.strip():
            return cls(((DERIVED_KEY_ID, derived_key(secret_key)),))
        return cls(parse_keys(keys))

    @property
    def current_key_id(self) -> str:
        return self.keys[0][0]

    def seal(self, plaintext: str, *, context: str) -> str:
        """``plaintext`` sealed under the first key, for ``context`` only."""
        key_id, key = self.keys[0]
        nonce = secrets.token_bytes(NONCE_BYTES)
        sealed = AESGCM(key).encrypt(nonce, plaintext.encode(), self._associated(key_id, context))
        return f"{_FORMAT}.{key_id}.{_b64encode(nonce + sealed)}"

    def open(self, sealed: str, *, context: str) -> str:
        """What ``sealed`` holds, if it was sealed for ``context`` under a listed key."""
        version, _, rest = sealed.partition(".")
        key_id, _, body = rest.partition(".")
        key = dict(self.keys).get(key_id)
        if version != _FORMAT or key is None or not body:
            raise SealError
        try:
            data = _b64decode(body)
            plaintext = AESGCM(key).decrypt(
                data[:NONCE_BYTES], data[NONCE_BYTES:], self._associated(key_id, context)
            )
            return plaintext.decode()
        except InvalidTag, ValueError:  # bad base64 and bad UTF-8 are ValueErrors too
            raise SealError from None

    def needs_resealing(self, sealed: str) -> bool:
        """Whether ``sealed`` is under a key other than the first: one to seal again in time."""
        return sealed.split(".", 2)[1:2] != [self.current_key_id]

    @staticmethod
    def _associated(key_id: str, context: str) -> bytes:
        # The format and key id are bound too, so neither can be swapped for another.
        return f"{_FORMAT}\x00{key_id}\x00{context}".encode()


def field_cipher(settings: Settings) -> FieldCipher:
    """The cipher the settings name: FIELD_ENCRYPTION_KEYS, or the key derived from SECRET_KEY."""
    keys = settings.field_encryption_keys
    return FieldCipher.from_config(
        None if keys is None else keys.get_secret_value(),
        secret_key=settings.secret_key.get_secret_value().encode(),
    )
