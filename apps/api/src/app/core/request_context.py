"""Request id, timing and one access-log line for every HTTP request.

A plain ASGI middleware rather than ``BaseHTTPMiddleware``, so it adds no overhead and sees every
response. The id comes from a well-formed ``X-Request-ID`` header (from the web app or the load
balancer) or is generated (UUIDv7). It is bound to every log line of the request, kept in
``request.state.request_id`` and returned in the ``X-Request-ID`` response header.
"""

import re
import time
import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.datastructures import Headers, MutableHeaders

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
# Probes hit these every few seconds; their access-log lines are debug-level.
PROBE_PATHS = frozenset({"/healthz", "/readyz"})

_WELL_FORMED_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")

logger = structlog.stdlib.get_logger("app.request")


def _route_template(scope: Scope) -> str:
    """The matched route's template (``/v1/bookings/{code}``), never the raw path with its ids."""
    route = scope.get("route")
    if route is not None:
        return str(getattr(route, "path", "unmatched"))
    # Plain Starlette routes (the OpenAPI schema, the docs) have fixed paths without ids.
    if "endpoint" in scope:
        return str(scope["path"])
    return "unmatched"


def request_id_of(scope: Scope) -> str | None:
    state = scope.get("state") or {}
    request_id = state.get("request_id")
    return request_id if isinstance(request_id, str) else None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _WELL_FORMED_ID.fullmatch(incoming) else str(uuid.uuid7())
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            log = logger.debug if scope["path"] in PROBE_PATHS else logger.info
            log(
                "request",
                method=scope["method"],
                route=_route_template(scope),
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            structlog.contextvars.unbind_contextvars("request_id")
