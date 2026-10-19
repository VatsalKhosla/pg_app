"""RFC 9457 problem details for every error response (ARCHITECTURE §15).

Raise an ``AppError`` subclass anywhere. ``install_error_handlers`` turns it, request validation
errors, unknown routes and unexpected exceptions into ``application/problem+json`` with a stable
machine-readable ``code``, the request id and, when tracing is on, the trace id. Unexpected
errors never reveal their message to the client.
"""

import http
from typing import TYPE_CHECKING, ClassVar

import sentry_sdk
import structlog
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import REQUEST_ID_HEADER, request_id_of
from app.core.schemas import ApiModel

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from fastapi import FastAPI, Request
    from starlette.types import Scope

PROBLEM_JSON = "application/problem+json"

logger = structlog.stdlib.get_logger(__name__)


class FieldError(ApiModel):
    """One invalid input. ``pointer`` locates a body field (JSON Pointer, e.g. ``/moveIn``);
    ``parameter`` names a query, path, header or cookie parameter."""

    detail: str
    code: str
    pointer: str | None = None
    parameter: str | None = None


class ProblemDetail(ApiModel):
    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str | None = None
    errors: tuple[FieldError, ...] | None = None
    request_id: str | None = None
    trace_id: str | None = None


class AppError(Exception):
    """An error reported to the client. Subclasses set ``status``, ``code`` and ``title``."""

    status: ClassVar[int] = 500
    code: ClassVar[str] = "INTERNAL_ERROR"
    title: ClassVar[str] = "Internal server error"

    def __init__(
        self, detail: str | None = None, *, headers: Mapping[str, str] | None = None
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.headers = dict(headers or {})


class UnauthenticatedError(AppError):
    status = 401
    code = "UNAUTHENTICATED"
    title = "Sign in required"


class ForbiddenError(AppError):
    """Signed in, but without the role a route needs. Someone else's record answers NotFoundError
    instead, so nobody learns that it exists."""

    status = 403
    code = "FORBIDDEN"
    title = "Not allowed"


class NotFoundError(AppError):
    status = 404
    code = "NOT_FOUND"
    title = "Not found"


class PayloadTooLargeError(AppError):
    status = 413
    code = "PAYLOAD_TOO_LARGE"
    title = "Request body too large"


class ServiceUnavailableError(AppError):
    status = 503
    code = "SERVICE_UNAVAILABLE"
    title = "Service unavailable"


# Stable codes for errors Starlette raises itself (unknown routes, wrong methods, ...).
_HTTP_CODES: Mapping[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    406: "NOT_ACCEPTABLE",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}


def problem_response(
    scope: Scope,
    *,
    status: int,
    code: str,
    title: str | None = None,
    detail: str | None = None,
    errors: Sequence[FieldError] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = request_id_of(scope)
    span = trace.get_current_span().get_span_context()
    problem = ProblemDetail(
        title=title or http.HTTPStatus(status).phrase,
        status=status,
        code=code,
        detail=detail,
        errors=tuple(errors) or None,
        request_id=request_id,
        trace_id=format(span.trace_id, "032x") if span.is_valid else None,
    )
    response_headers = dict(headers or {})
    if request_id is not None:
        response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=status,
        media_type=PROBLEM_JSON,
        headers=response_headers,
    )


def _escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _field_error(error: Mapping[str, object]) -> FieldError:
    location = error.get("loc")
    parts = [str(part) for part in location] if isinstance(location, (list, tuple)) else []
    source, path = (parts[0], parts[1:]) if parts else ("body", [])
    detail, code = str(error.get("msg", "Invalid value")), str(error.get("type", "invalid"))
    if source == "body":
        pointer = "/" + "/".join(_escape_pointer_token(part) for part in path)
        return FieldError(detail=detail, code=code, pointer=pointer)
    return FieldError(detail=detail, code=code, parameter=".".join(path) or source)


async def _on_app_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # registered for AppError only
        raise exc
    return problem_response(
        request.scope,
        status=exc.status,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        headers=exc.headers,
    )


async def _on_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # registered for RequestValidationError only
        raise exc
    # Never echo the rejected input: it may contain personal data.
    return problem_response(
        request.scope,
        status=422,
        code="VALIDATION_ERROR",
        title="Request is invalid",
        detail="Correct the listed fields and try again.",
        errors=[_field_error(error) for error in exc.errors()],
    )


async def _on_http_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # registered for HTTPException only
        raise exc
    return problem_response(
        request.scope,
        status=exc.status_code,
        code=_HTTP_CODES.get(exc.status_code, "HTTP_ERROR"),
        headers=exc.headers,
    )


async def _on_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Runs outside RequestContextMiddleware, so the request id is passed explicitly.
    logger.error("unhandled error", request_id=request_id_of(request.scope), exc_info=exc)
    sentry_sdk.capture_exception(exc)
    return problem_response(request.scope, status=500, code=AppError.code, title=AppError.title)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _on_app_error)
    app.add_exception_handler(RequestValidationError, _on_validation_error)
    app.add_exception_handler(StarletteHTTPException, _on_http_error)
    app.add_exception_handler(Exception, _on_unexpected_error)
