"""Running the outbox's due jobs in a test, as the worker process runs them."""

from collections.abc import Mapping, Sequence
from datetime import datetime

from fastapi import FastAPI

from app.core.outbox import OutboxWorker
from app.core.texts import ConsoleTexts, Texts
from app.core.web_cache import WebCache
from app.jobs import build_registry
from tests.storage import BUCKETS, MemoryStorage


class RecordedWebCache:
    """The web app, as a test sees it: the tags it was asked to revalidate, in order."""

    def __init__(self) -> None:
        self.tags: list[list[str]] = []

    async def revalidate(self, tags: Sequence[str], *, now: datetime) -> None:
        self.tags.append(list(tags))


class RecordedTexts:
    """Text messages, as a test sees them: who, which template and its blanks, in order."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, str]]] = []

    async def send(self, phone_e164: str, template: str, values: Mapping[str, str]) -> None:
        self.sent.append((phone_e164, template, dict(values)))


async def run_due_jobs(
    app: FastAPI, *, web_cache: WebCache | None = None, texts: Texts | None = None
) -> None:
    """Every job that's due at the app's clock, until none is left."""
    worker = OutboxWorker(
        sessionmaker=app.state.sessionmaker,
        registry=build_registry(
            storage=MemoryStorage(),
            buckets=BUCKETS,
            web_cache=web_cache or RecordedWebCache(),
            texts=texts or ConsoleTexts(),
        ),
        clock=app.state.clock,
        worker_id="test",
        batch_size=50,
    )
    while await worker.run_once():
        pass
