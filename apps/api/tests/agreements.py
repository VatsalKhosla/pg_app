"""Agreement texts for tests: owner agreement versions that aren't written yet, such as the next
one, or a reviewed one for a production-like app (ADR 0025); and rent agreement templates the same
way (ADR 0070)."""

from app.modules.catalog.domain.agreements import Agreement


class FixedAgreements:
    """An AgreementLibrary of the texts given."""

    def __init__(self, *agreements: Agreement) -> None:
        self._agreements = {agreement.version: agreement for agreement in agreements}

    def get(self, version: str) -> Agreement | None:
        return self._agreements.get(version)


class FixedTemplates:
    """A rent agreement TemplateLibrary of the (version, template) pairs given."""

    def __init__(self, *templates: tuple[str, str]) -> None:
        self._templates = dict(templates)

    def get(self, version: str) -> str | None:
        return self._templates.get(version)
