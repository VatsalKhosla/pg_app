"""Running the outbox's due jobs in a test, as the worker process runs them."""

from fastapi import FastAPI

from app.core.outbox import OutboxWorker
from app.jobs import build_registry
from tests.storage import BUCKETS, MemoryStorage


async def run_due_jobs(app: FastAPI) -> None:
    """Every job that's due at the app's clock, until none is left."""
    worker = OutboxWorker(
        sessionmaker=app.state.sessionmaker,
        registry=build_registry(storage=MemoryStorage(), buckets=BUCKETS),
        clock=app.state.clock,
        worker_id="test",
        batch_size=50,
    )
    while await worker.run_once():
        pass
