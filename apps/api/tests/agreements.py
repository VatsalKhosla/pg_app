"""Owner agreement texts for tests (ADR 0025): versions that aren't written yet, such as the next
one, or a reviewed one for a production-like app."""

from app.modules.catalog.domain.agreements import Agreement


class FixedAgreements:
    """An AgreementLibrary of the texts given."""

    def __init__(self, *agreements: Agreement) -> None:
        self._agreements = {agreement.version: agreement for agreement in agreements}

    def get(self, version: str) -> Agreement | None:
        return self._agreements.get(version)
