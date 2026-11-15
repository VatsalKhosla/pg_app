"""What the identity module needs from the outside world, as interfaces (ARCHITECTURE §1)."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.identity.domain.staff import GoogleAccount


class OtpSender(Protocol):
    """Delivers a sign-in code to a phone. Production uses an SMS provider with a DLT-registered
    template (the founders choose it); development writes the code to the log."""

    # Whether the code may go back to whoever asked for it, because nothing really sends it: only
    # the console sender, refused in every deployed environment, and the screen sender for a test
    # site, refused in production (ADR 0055).
    shows_code: bool

    async def send(self, phone_e164: str, code: str) -> None:
        """Deliver ``code``, or raise if it couldn't be handed to the provider."""
        ...


class EmailCodeSender(Protocol):
    """Delivers a sign-in code to an email address (ADR 0068), through the site's mailer."""

    # As for OtpSender: true only where nothing really sends the code (local development, and a
    # test site before its mail is set up).
    shows_code: bool
    # Whether codes can reach anyone at all: false where mail isn't set up and codes aren't shown.
    available: bool

    async def send(self, email: str, code: str) -> None:
        """Deliver ``code``, or raise if the mail server didn't take it."""
        ...


class GoogleSignIn(Protocol):
    """Google's side of signing in with Google (staff, and since ADR 0068 anyone): OpenID
    Connect's authorization code flow with PKCE."""

    def authorization_url(
        self, *, state: str, nonce: str, code_challenge: str, any_account: bool = False
    ) -> str:
        """Where to send the browser to sign in at Google. Google's account chooser offers only
        the staff Workspace's accounts unless ``any_account``."""
        ...

    async def finish(self, code: str, *, code_verifier: str, nonce: str) -> GoogleAccount:
        """Redeem the code Google sent back, and return the account its ID token names once the
        token passes every check. Raises StaffSignInExpiredError for a code or token that is
        stale or belongs to another sign-in, and ServiceUnavailableError when Google can't be
        reached or answers something it shouldn't."""
        ...
