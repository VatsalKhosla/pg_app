"""The owner agreement's versions (ADR 0025): one Markdown file per version in data/agreements.

A version's file is never edited once an owner may have accepted it: a change is a new file, made
current by OWNER_AGREEMENT_VERSION. The brand name is filled in from BRAND_NAME, so renaming the
brand changes the text; publish a new version when it does.
"""

from pathlib import Path
from typing import Final, Protocol

from app.config import BRAND_NAME
from app.modules.catalog.domain.agreements import VERSION_PATTERN, Agreement

AGREEMENTS_DIR: Final = Path(__file__).parent / "data" / "agreements"


class AgreementLibrary(Protocol):
    """Where the agreement's versions come from: these files, or fixed texts in a test."""

    def get(self, version: str) -> Agreement | None: ...


class FileAgreements:
    def __init__(self, directory: Path = AGREEMENTS_DIR, *, brand: str = BRAND_NAME) -> None:
        self._directory = directory
        self._brand = brand
        self._read: dict[str, Agreement] = {}

    def get(self, version: str) -> Agreement | None:
        if not VERSION_PATTERN.fullmatch(version):
            return None
        if version not in self._read:
            path = self._directory / f"{version}.md"
            if not path.is_file():
                return None
            text = path.read_text(encoding="utf-8").replace("{brand}", self._brand)
            self._read[version] = Agreement(version, text)
        return self._read[version]
