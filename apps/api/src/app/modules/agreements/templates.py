"""The rent agreement's templates (ADR 0070): one Markdown file per version in data/templates.

A version's file is never edited once someone may have signed a text made from it: a change is a
new file, made current by CURRENT_VERSION in the same review. A unit test pins every file's
SHA-256, so editing one fails until it becomes a new version. Agreements already signed keep the
text they were signed with, whatever the current version.

Versions starting "draft" haven't been reviewed by a lawyer: the text says DRAFT, and production
refuses to start while the current version is one (app/main.py).
"""

import re
from pathlib import Path
from typing import Final, Protocol

TEMPLATES_DIR: Final = Path(__file__).parent / "data" / "templates"
# The version new agreements are written from.
CURRENT_VERSION: Final = "draft-1"
VERSION_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9.-]{0,63}")


def is_draft(version: str) -> bool:
    return version.startswith("draft")


class TemplateLibrary(Protocol):
    """Where the templates come from: these files, or fixed texts in a test."""

    def get(self, version: str) -> str | None: ...


class FileTemplates:
    def __init__(self, directory: Path = TEMPLATES_DIR) -> None:
        self._directory = directory
        self._read: dict[str, str] = {}

    def get(self, version: str) -> str | None:
        if not VERSION_PATTERN.fullmatch(version):
            return None
        if version not in self._read:
            path = self._directory / f"{version}.md"
            if not path.is_file():
                return None
            self._read[version] = path.read_text(encoding="utf-8")
        return self._read[version]


class Templates:
    """The library and the version in force, as the services and jobs take them."""

    def __init__(
        self, library: TemplateLibrary | None = None, *, version: str = CURRENT_VERSION
    ) -> None:
        self.library = library or FileTemplates()
        self.version = version
        if self.library.get(version) is None:
            msg = f"no rent agreement template for version {version}"
            raise LookupError(msg)

    @property
    def current(self) -> str:
        template = self.library.get(self.version)
        if template is None:  # pragma: no cover - checked when made
            raise LookupError(self.version)
        return template
