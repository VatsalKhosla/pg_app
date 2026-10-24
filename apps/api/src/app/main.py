"""HTTP API entrypoint and composition root: ``uvicorn app.main:create_app --factory``."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Final

import httpx
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
from app.core.human_check import DisabledHumanCheck, TurnstileCheck
from app.core.logging import configure_logging
from app.core.openapi import PROBLEM_RESPONSES, Api, operation_id
from app.core.ratelimit import RateLimiter
from app.core.redis import create_redis
from app.core.request_context import PROBE_PATHS, REQUEST_ID_HEADER, RequestContextMiddleware
from app.core.security import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.telemetry import SERVICE_VERSION, configure_sentry, configure_tracing
from app.modules.compliance.router import router as compliance_router
from app.modules.geo.router import router as geo_router
from app.modules.identity.adapters.console_otp import ConsoleOtpSender
from app.modules.identity.adapters.google_oidc import GoogleOidc
from app.modules.identity.adapters.unavailable_otp import UnavailableOtpSender
from app.modules.identity.auth import authenticate_session
from app.modules.identity.router import GOOGLE_CALLBACK_PATH
from app.modules.identity.router import router as identity_router
from app.modules.media.adapters.s3 import S3Storage
from app.modules.media.router import router as media_router
from app.modules.media.service import Buckets
from app.modules.system.router import router as system_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI
    from starlette.types import Scope

# Headers the web app may send on cross-origin requests (CSRF arrives in step 1.1, idempotency
# keys in step 0.4).
CORS_ALLOWED_HEADERS = ["Content-Type", CSRF_HEADER, "Idempotency-Key", REQUEST_ID_HEADER]
CORS_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
# Outside providers: connect within 3 s, answer within 10 s (the backend rules).
PROVIDER_TIMEOUT = httpx.Timeout(10.0, connect=3.0)

logger = structlog.stdlib.get_logger(__name__)


def _is_probe(scope: Scope) -> bool:
    return scope.get("path") in PROBE_PATHS


# Every module's routes, in the order the OpenAPI schema lists them.
ROUTERS: Final = (system_router, identity_router, compliance_router, geo_router, media_router)


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
        # One HTTP client per outside provider, so a slow one can't use up another's connections.
        turnstile_http = httpx.AsyncClient(timeout=PROVIDER_TIMEOUT)
        google_http = httpx.AsyncClient(timeout=PROVIDER_TIMEOUT)
        tracer_provider = configure_tracing(settings, engine=engine)
        app.state.clock = clock
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker
        app.state.redis = redis
        app.state.rate_limiter = RateLimiter(
            redis, clock, secret=settings.secret_key.get_secret_value().encode()
        )
        app.state.flags = FeatureFlags(sessionmaker, clock)
        app.state.storage = S3Storage.from_settings(settings)
        app.state.media_buckets = Buckets.from_settings(settings)
        app.state.human_check = (
            DisabledHumanCheck()
            if settings.turnstile_secret_key is None
            else TurnstileCheck(
                turnstile_http, settings.turnstile_secret_key, hostnames=settings.web_hostnames
            )
        )
        app.state.otp_sender = (
            ConsoleOtpSender() if settings.otp_sender == "console" else UnavailableOtpSender()
        )
        app.state.google_sign_in = (
            None
            if settings.google_client_id is None or settings.google_client_secret is None
            else GoogleOidc(
                google_http,
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                redirect_uri=f"{settings.api_url}{GOOGLE_CALLBACK_PATH}",
                clock=clock,
                hosted_domain=settings.google_hosted_domain_hint,
            )
        )
        logger.info("api started", environment=settings.app_env, version=SERVICE_VERSION)
        try:
            yield
        finally:
            await turnstile_http.aclose()
            await google_http.aclose()
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
    app.state.secret_key = settings.secret_key.get_secret_value().encode()
    # Who a request's session belongs to, for every module's CurrentActor.
    app.state.authenticate = authenticate_session
    app.state.site_url = settings.site_url
    app.state.privacy_notice_version = settings.privacy_notice_version
    app.state.staff_google_domains = settings.staff_google_domains
    app.state.staff_google_emails = settings.staff_google_emails
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
    for router in ROUTERS:
        app.include_router(router)
    return app
