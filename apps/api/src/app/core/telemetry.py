"""Tracing and metrics (OpenTelemetry) and error reporting (Sentry); all stay off until
configured.

FastAPI traces requests itself into whichever tracer provider is set (ARCHITECTURE §19). This
module sets one up only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is configured, exporting over
OTLP/HTTP, and adds SQLAlchemy and Redis spans. With the same endpoint, the API and the worker
each export their metrics every minute: the outbox's runs, failures and lag, and the bookings'
changes and jobs (ADR 0052). Sentry starts only with a DSN, sends no default PII and masks phone
numbers in every event.
"""

from importlib.metadata import version
from typing import TYPE_CHECKING, cast

import sentry_sdk
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.pii import mask_pii

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.config import Settings

SERVICE_VERSION = version("pg-platform-api")
# How often each process sends its metrics.
METRICS_INTERVAL_MS = 60_000


def _resource(settings: Settings, **more: str) -> Resource:
    return Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": SERVICE_VERSION,
            "deployment.environment.name": settings.app_env,
            **more,
        }
    )


def configure_tracing(settings: Settings, *, engine: AsyncEngine) -> TracerProvider | None:
    if settings.otel_exporter_otlp_endpoint is None:
        return None
    provider = TracerProvider(resource=_resource(settings))
    # The exporter reads OTEL_EXPORTER_OTLP_ENDPOINT (and _HEADERS) itself.
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=provider)
    RedisInstrumentor().instrument(tracer_provider=provider)
    return provider


def configure_metrics(settings: Settings, *, process: str) -> MeterProvider | None:
    """The process's metrics, sent every minute, its name (``api`` or ``worker``) on each; None
    without an endpoint. Shut the provider down on the way out, to send the last ones."""
    if settings.otel_exporter_otlp_endpoint is None:
        return None
    provider = MeterProvider(
        resource=_resource(settings, **{"process.role": process}),
        # The exporter reads OTEL_EXPORTER_OTLP_ENDPOINT (and _HEADERS) itself.
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(), export_interval_millis=METRICS_INTERVAL_MS
            )
        ],
    )
    metrics.set_meter_provider(provider)
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
