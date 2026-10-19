# ADR 0014: Sessions and CSRF protection

- Status: accepted
- Date: 2026-10-19
- Build step: 1.1 (users, roles, sessions)

## Context

Students, parents and owners sign in with their phone (step 1.2), and staff with Google (step 1.3); both end in a session. ARCHITECTURE §12 fixes the outline: opaque tokens with only a hash stored, `HttpOnly; Secure; SameSite=Lax` cookies on the parent domain, a 30-day sliding expiry, rotation, logout, log out everywhere, a session list and double-submit CSRF tokens. This ADR records the details.

## Decision

1. **Tokens.**
   - A session token is 256 random bits (`secrets.token_urlsafe(32)`, 43 characters).
   - The `sessions` table stores only its SHA-256 (unique). An unkeyed hash is enough: a random token can't be recovered from it, and session validity doesn't depend on `SECRET_KEY`, so rotating the key doesn't sign everyone out.
   - Malformed tokens are refused before any database query.
2. **Cookies** (`app/core/cookies.py`):
   - Names: `__Secure-session` (HttpOnly) and `__Secure-csrf` (readable by the web app).
   - Attributes: `Secure`, `SameSite=Lax`, `Path=/`.
   - Domain: `SESSION_COOKIE_DOMAIN` (the parent domain) when the web app and the API are on sibling subdomains, host-only otherwise.
   - The `__Secure-` prefix makes browsers refuse the cookies from insecure origins.
   - The web server forwards exactly these two cookies when it calls the API on a visitor's behalf.
3. **Lifetimes.** These are pure rules in `identity/domain/sessions.py`:
   - User sessions end after 30 idle days. Activity moves the expiry at most every 10 minutes, and the cookie is sent again with the new lifetime, so the browser keeps it as long as the server does.
   - Staff sessions end 12 hours after sign-in, however active.
   - A suspended user's sessions stop working at once.
4. **Rotation.**
   - Signing in ends the browser's previous session (`replacing`), so a token planted before sign-in never becomes signed in (session fixation).
   - `rotate()` gives a live session a new token in place, keeping its identity in the session list. It is for role changes.
5. **Ending sessions:**
   - Logout ends this browser's session and clears both cookies. It is safe to repeat.
   - "Log out everywhere" ends every session of the user.
   - The session list ends a single session; another user's session answers 404.
   - Ended and expired sessions, with their IP address and user agent, are deleted 30 days later by a daily job (DPDP: no longer than needed).
6. **CSRF uses OWASP's signed double-submit pattern** (`app/core/csrf.py`):
   - `GET /v1/auth/csrf` sets the token. Unsafe requests must echo it in `X-CSRF-Token`.
   - The token is HMAC-signed with `SECRET_KEY` and bound to the session cookie it was issued with (by a hash, so the check needs no database). A cookie planted by a sibling subdomain, or kept from an earlier session, fails.
   - The check is a dependency of the whole FastAPI app: deny by default, after routing, so 404 and 405 still work. Only provider webhooks (`/v1/webhooks/`) are exempt.
   - A unit test sends every unsafe route of the real app a tokenless request and expects `403 CSRF_TOKEN_INVALID`.
7. **The authenticated principal is an `Actor`** (`app/core/actor.py`): user, roles and session. `CurrentActor` resolves it, answering `401 UNAUTHENTICATED` without a live session. Other modules' policies depend on `Actor`, not on the identity tables.

## Consequences

- One database round trip authenticates a request (session, user, roles). A write happens at most every 10 minutes per session.
- The web app must fetch a CSRF token (`GET /v1/auth/csrf`) after signing in or out, because tokens are bound to the session. Server-side calls that change state must forward the cookie and the header.
- FastAPI 0.143 nests included routers. Anything that enumerates routes, such as the CSRF test and step 1.4's authorization matrix, walks them with `fastapi.routing.iter_route_contexts`.
- Local development needs a secure origin for `__Secure-` cookies: `http://localhost` qualifies in current browsers.
