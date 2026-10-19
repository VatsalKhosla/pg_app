"""Telling people from bots before abusable actions, such as sending an OTP (ARCHITECTURE §12).

The browser solves a Cloudflare Turnstile challenge and sends its token with the request; the API
checks the token with Cloudflare's siteverify endpoint. Tokens live 5 minutes and work once, and
count only for the form (the widget's ``action``) and the site (``hostname``) they were solved on,
as Cloudflare advises. Without a secret key, which only local development and tests may run with,
every token passes.
"""

import asyncio
import uuid
from typing import TYPE_CHECKING, Final, Protocol

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError

from app.core.errors import AppError, ServiceUnavailableError

if TYPE_CHECKING:
    from pydantic import SecretStr

SITEVERIFY_URL: Final = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
MAX_TOKEN_LENGTH: Final = 2048
_ATTEMPTS: Final = 3
_RETRY_DELAY_SECONDS: Final = 0.2
# Error codes that mean our secret key is wrong, not the visitor's token.
_SECRET_REFUSED: Final = frozenset({"missing-input-secret", "invalid-input-secret"})

logger = structlog.stdlib.get_logger(__name__)


class HumanCheckFailedError(AppError):
    status = 400
    code = "HUMAN_CHECK_FAILED"
    title = "Couldn't confirm you're not a bot"


class HumanCheck(Protocol):
    async def verify(self, token: str, *, remote_ip: str | None, action: str) -> bool:
        """Whether ``token`` was solved by a person, on this site, for the form ``action``."""


class _Metadata(BaseModel):
    result_with_testing_key: bool = False


class _Outcome(BaseModel):
    """The parts of siteverify's answer the check reads; the rest is ignored."""

    success: bool
    error_codes: list[str] = Field(default_factory=list, alias="error-codes")
    action: str | None = None
    hostname: str | None = None
    metadata: _Metadata | None = None


class TurnstileCheck:
    """Cloudflare Turnstile. Retries brief network trouble and Cloudflare's own errors with one
    idempotency key; if Cloudflare stays unreachable, refuses (503) rather than letting bots in.

    ``hostnames`` are the web app's; a token solved anywhere else fails.
    """

    def __init__(
        self, http: httpx.AsyncClient, secret: SecretStr, *, hostnames: frozenset[str]
    ) -> None:
        self._http = http
        self._secret = secret
        self._hostnames = hostnames

    async def verify(self, token: str, *, remote_ip: str | None, action: str) -> bool:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            return False
        form = {
            "secret": self._secret.get_secret_value(),
            "response": token,
            "idempotency_key": str(uuid.uuid4()),
        }
        if remote_ip is not None:
            form["remoteip"] = remote_ip
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                response = await self._http.post(SITEVERIFY_URL, data=form)
                if response.status_code < 500:
                    outcome = _Outcome.model_validate_json(response.content)
                    if "internal-error" not in outcome.error_codes:
                        return self._accepts(outcome, action)
            except (httpx.HTTPError, ValidationError) as error:
                logger.warning("human check request failed", attempt=attempt, error=str(error))
            if attempt < _ATTEMPTS:
                await asyncio.sleep(_RETRY_DELAY_SECONDS * attempt)
        raise ServiceUnavailableError("Please try again in a moment.")

    def _accepts(self, outcome: _Outcome, action: str) -> bool:
        if _SECRET_REFUSED.intersection(outcome.error_codes):
            # Our configuration, not the visitor: alert, and don't blame them for it.
            logger.error("Turnstile refused the secret key; check TURNSTILE_SECRET_KEY")
            raise ServiceUnavailableError("Please try again in a moment.")
        if not outcome.success:
            logger.info("human check failed", errors=outcome.error_codes)
            return False
        # Cloudflare's test keys report no action and a placeholder hostname, and say so. Only a
        # test secret gets this answer: real secrets refuse test tokens.
        if outcome.metadata is not None and outcome.metadata.result_with_testing_key:
            return True
        if outcome.action != action or outcome.hostname not in self._hostnames:
            logger.warning(
                "human check solved for another form or site",
                action=outcome.action,
                expected_action=action,
                hostname=outcome.hostname,
            )
            return False
        return True


class DisabledHumanCheck:
    """Lets every request through. Local development and tests only (app/config.py)."""

    async def verify(self, token: str, *, remote_ip: str | None, action: str) -> bool:
        return True
