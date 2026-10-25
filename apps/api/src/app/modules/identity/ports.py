"""What the identity module needs from the outside world, as interfaces (ARCHITECTURE §1)."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.identity.domain.staff import GoogleAccount


class OtpSender(Protocol):
    """Delivers a sign-in code to a phone. Production uses an SMS provider with a DLT-registered
    template (the founders choose it); development writes the code to the log."""

    # Whether the code may go back to whoever asked for it, because nothing really sends it: only
    # the console sender, which settings refuse in every deployed environment.
    shows_code: bool

    async def send(self, phone_e164: str, code: str) -> None:
        """Deliver ``code``, or raise if it couldn't be handed to the provider."""
        ...


class GoogleSignIn(Protocol):
    """Google's side of staff sign-in: OpenID Connect's authorization code flow with PKCE."""

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        """Where to send the browser to sign in at Google."""
        ...

    async def finish(self, code: str, *, code_verifier: str, nonce: str) -> GoogleAccount:
        """Redeem the code Google sent back, and return the account its ID token names once the
        token passes every check. Raises StaffSignInExpiredError for a code or token that is
        stale or belongs to another sign-in, and ServiceUnavailableError when Google can't be
        reached or answers something it shouldn't."""
        ...
