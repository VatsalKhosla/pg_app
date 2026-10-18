"""Tracing (OpenTelemetry) and error reporting (Sentry); both stay off until configured.

FastAPI traces requests itself into whichever tracer provider is set (ARCHITECTURE §19). This
module sets one up only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is configured, exporting over
OTLP/HTTP, and adds SQLAlchemy and Redis spans. Sentry starts only with a DSN, sends no default
PII and masks phone numbers in every event.
"""

from importlib.metadata import version
from typing import TYPE_CHECKING, cast

import sentry_sdk
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.pii import mask_pii

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.config import Settings

SERVICE_VERSION = version("pg-platform-api")


def configure_tracing(settings: Settings, *, engine: AsyncEngine) -> TracerProvider | None:
    if settings.otel_exporter_otlp_endpoint is None:
        return None
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": SERVICE_VERSION,
                "deployment.environment.name": settings.app_env,
            }
        )
    )
    # The exporter reads OTEL_EXPORTER_OTLP_ENDPOINT (and _HEADERS) itself.
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=provider)
    RedisInstrumentor().instrument(tracer_provider=provider)
    return provider


def scrub_event(event: Event, _hint: Hint) -> Event:
    return cast("Event", mask_pii(event))


def configure_sentry(settings: Settings) -> None:
    if settings.sentry_dsn is None:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.app_env,
        release=f"pg-platform-api@{SERVICE_VERSION}",
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=scrub_event,
    )
