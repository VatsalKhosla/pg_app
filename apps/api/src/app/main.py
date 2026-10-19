"""HTTP API entrypoint and composition root: ``uvicorn app.main:create_app --factory``."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import Depends
from starlette.middleware.cors import CORSMiddleware

from app.config import BRAND_NAME, Settings, get_settings
from app.core.clock import Clock, SystemClock
from app.core.cookies import CSRF_HEADER, CookiePolicy
from app.core.csrf import require_csrf_token
from app.core.db import create_engine, create_sessionmaker
from app.core.errors import install_error_handlers
from app.core.flags import FeatureFlags
from app.core.logging import configure_logging
from app.core.openapi import PROBLEM_RESPONSES, Api, operation_id
from app.core.ratelimit import RateLimiter
from app.core.redis import create_redis
from app.core.request_context import PROBE_PATHS, REQUEST_ID_HEADER, RequestContextMiddleware
from app.core.security import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.telemetry import SERVICE_VERSION, configure_sentry, configure_tracing
from app.modules.identity.router import router as identity_router
from app.modules.system.router import router as system_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI
    from starlette.types import Scope

# Headers the web app may send on cross-origin requests (CSRF arrives in step 1.1, idempotency
# keys in step 0.4).
CORS_ALLOWED_HEADERS = ["Content-Type", CSRF_HEADER, "Idempotency-Key", REQUEST_ID_HEADER]
CORS_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]

logger = structlog.stdlib.get_logger(__name__)


def _is_probe(scope: Scope) -> bool:
    return scope.get("path") in PROBE_PATHS


def create_app(settings: Settings | None = None, *, clock: Clock | None = None) -> FastAPI:
    """Build the API. Tests pass their own ``settings`` and a ``FrozenClock``."""
    settings = settings or get_settings()
    clock = clock or SystemClock()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    configure_sentry(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings, application_name=settings.otel_service_name)
        sessionmaker = create_sessionmaker(engine)
        redis = create_redis(settings)
        tracer_provider = configure_tracing(settings, engine=engine)
        app.state.clock = clock
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker
        app.state.redis = redis
        app.state.rate_limiter = RateLimiter(
            redis, clock, secret=settings.secret_key.get_secret_value().encode()
        )
        app.state.flags = FeatureFlags(sessionmaker, clock)
        logger.info("api started", environment=settings.app_env, version=SERVICE_VERSION)
        try:
            yield
        finally:
            await redis.aclose()
            await engine.dispose()
            if tracer_provider is not None:
                tracer_provider.shutdown()
            logger.info("api stopped")

    interactive_docs = settings.app_env != "production"
    app = Api(
        title=f"{BRAND_NAME} API",
        version=SERVICE_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if interactive_docs else None,
        redoc_url="/redoc" if interactive_docs else None,
        responses=PROBLEM_RESPONSES,
        generate_unique_id_function=operation_id,
        # Every route, including ones added later: state-changing requests need a CSRF token.
        dependencies=[Depends(require_csrf_token)],
        telemetry={"exclude": _is_probe},
    )
    app.state.cookies = CookiePolicy(domain=settings.session_cookie_domain)
    app.state.csrf_secret = settings.secret_key.get_secret_value().encode()
    install_error_handlers(app)
    # Added innermost first, so a request passes RequestContext, SecurityHeaders, CORS and then
    # BodySizeLimit before reaching a route.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=CORS_ALLOWED_METHODS,
        allow_headers=CORS_ALLOWED_HEADERS,
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_deployed)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(system_router)
    app.include_router(identity_router)
    return app
