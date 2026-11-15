"""Google and a browser, as the sign-in tests see them (tests/integration/test_staff_sign_in.py and
test_people_sign_in.py)."""

import base64
import hashlib
import secrets
from typing import Any

import httpx

from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import issue_csrf_token
from app.modules.identity.domain.staff import GoogleAccount
from app.modules.identity.errors import StaffSignInExpiredError
from tests.conftest import TEST_SECRET_KEY


class FakeGoogle:
    """Google, as far as the API can tell. ``choose`` plays the person picking an account at
    Google, for the sign-in the API started last."""

    def __init__(self) -> None:
        self._started: tuple[str, str] | None = None
        self._codes: dict[str, tuple[GoogleAccount, str, str]] = {}
        # Whether the last sign-in offered any Google account, not only the staff Workspace's.
        self.any_account = False

    def authorization_url(
        self, *, state: str, nonce: str, code_challenge: str, any_account: bool = False
    ) -> str:
        self._started = (nonce, code_challenge)
        self.any_account = any_account
        return f"https://accounts.google.test/o/oauth2/v2/auth?state={state}"

    def choose(self, account: GoogleAccount) -> str:
        assert self._started is not None, "no sign-in was started"
        code = secrets.token_urlsafe(16)
        self._codes[code] = (account, *self._started)
        return code

    async def finish(self, code: str, *, code_verifier: str, nonce: str) -> GoogleAccount:
        # A code works once; the verifier must hash to the challenge, and the nonce must match.
        issued = self._codes.pop(code, None)
        if issued is None:
            raise StaffSignInExpiredError
        account, issued_nonce, challenge = issued
        digest = hashlib.sha256(code_verifier.encode()).digest()
        if base64.urlsafe_b64encode(digest).decode().rstrip("=") != challenge:
            raise StaffSignInExpiredError
        if nonce != issued_nonce:
            raise StaffSignInExpiredError
        return account


class Browser:
    """One browser: its own cookies, kept by hand, so a test says exactly what is sent."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self.cookies: dict[str, str] = {}

    async def request(
        self, method: str, path: str, *, csrf: bool = False, **kwargs: Any
    ) -> httpx.Response:
        headers: dict[str, str] = dict(kwargs.pop("headers", {}))
        if csrf:
            token = issue_csrf_token(TEST_SECRET_KEY.encode(), self.cookies.get(SESSION_COOKIE))
            self.cookies[CSRF_COOKIE] = token
            headers[CSRF_HEADER] = token
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        self._client.cookies.clear()
        response = await self._client.request(method, path, headers=headers, **kwargs)
        self._client.cookies.clear()
        for header in response.headers.get_list("set-cookie"):
            name, _, rest = header.partition("=")
            value = rest.split(";", 1)[0]
            if "max-age=0" in header.lower():
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = value
        return response

    def other(self) -> Browser:
        """Another browser, on the same network."""
        return Browser(self._client)
