"""HTTP hardening for the API: security headers and a request body limit (ARCHITECTURE §17).

Both are plain ASGI middleware. The headers suit a JSON API: nothing may frame, embed or sniff
its responses, and nothing is cached unless a route sets its own ``Cache-Control``.
"""

from typing import TYPE_CHECKING

from starlette.datastructures import Headers, MutableHeaders

from app.core.errors import PayloadTooLargeError, problem_response

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.types import ASGIApp, Message, Receive, Scope, Send

COMMON_HEADERS: Mapping[str, str] = {
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
HSTS = "max-age=63072000; includeSubDomains"
# The interactive docs (not served in production) are HTML pages that load Swagger UI or ReDoc.
DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        strict_csp = scope["path"] not in DOCS_PATHS

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in COMMON_HEADERS.items():
                    headers.setdefault(name, value)
                if strict_csp:
                    headers.setdefault("Content-Security-Policy", API_CSP)
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Refuse request bodies over ``max_bytes`` with 413, with or without a Content-Length."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.detail = f"Request bodies are limited to {max_bytes} bytes."

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            response = problem_response(
                scope,
                status=PayloadTooLargeError.status,
                code=PayloadTooLargeError.code,
                title=PayloadTooLargeError.title,
                detail=self.detail,
            )
            await response(scope, receive, send)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # Raised while the route reads its body, so the AppError handler answers.
                    raise PayloadTooLargeError(self.detail)
            return message

        await self.app(scope, counting_receive, send)
