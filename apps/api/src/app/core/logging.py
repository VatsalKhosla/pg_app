"""Structured logging (structlog): JSON lines in deployed environments, readable lines locally.

Every line carries the request id when there is one, and the trace id when tracing is on. Phone
numbers are masked to their last four digits before anything is written (CLAUDE.md). uvicorn,
SQLAlchemy and Alembic log through the same pipeline, so a process writes one format.
"""

import logging
import sys
from typing import TYPE_CHECKING, Literal

import structlog
from opentelemetry import trace

from app.core.pii import mask_pii

if TYPE_CHECKING:
    from structlog.typing import EventDict, Processor, WrappedLogger

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["json", "console"]


def _mask_pii(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    return {key: mask_pii(value) for key, value in event_dict.items()}


def _add_trace_id(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event_dict.setdefault("trace_id", format(context.trace_id, "032x"))
    return event_dict


def configure_logging(*, level: LogLevel, fmt: LogFormat) -> None:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_trace_id,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    exceptions: Processor = (
        structlog.processors.dict_tracebacks
        if fmt == "json"
        else structlog.processors.format_exc_info
    )
    renderer: Processor = (
        structlog.processors.JSONRenderer() if fmt == "json" else structlog.dev.ConsoleRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            exceptions,
            _mask_pii,  # after the traceback is rendered, so tracebacks are masked too
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    # RequestContextMiddleware writes one line per request instead of uvicorn's access log.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
