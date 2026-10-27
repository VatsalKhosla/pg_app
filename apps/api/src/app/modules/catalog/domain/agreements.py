"""The owner agreement (step 2.6, ADR 0025): one text per version, which owners accept by clicking.

An acceptance records the version, the SHA-256 of the exact text shown, when, from which IP and
with which user agent (PRODUCT_CONTEXT §6). A new version asks every owner to accept again.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Final

VERSION_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9.-]{0,63}")
SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}")
# Longer user agents are cut, not refused: they only help recognise the device.
USER_AGENT_MAX_LENGTH: Final = 512


@dataclass(frozen=True, slots=True)
class Agreement:
    version: str
    # Markdown, as shown to owners.
    text: str

    @property
    def sha256(self) -> str:
        """What an acceptance names: the hash of exactly this text, in UTF-8."""
        return hashlib.sha256(self.text.encode()).hexdigest()


def needs_acceptance(accepted_version: str | None, current_version: str) -> bool:
    """Whether an owner must accept the agreement again: always, once a new version is current."""
    return accepted_version != current_version
