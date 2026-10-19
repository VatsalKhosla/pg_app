# ADR 0016: Staff sign-in with Google, or a phone code and an authenticator app

- Status: accepted
- Date: 2026-10-19
- Build step: 1.3 (staff sign-in)

## Context

Staff are field agents, ops and admins; at first, the founders. They run listings, visits, bookings, disputes and refunds, so a staff account is worth far more to an attacker than a student's.

ARCHITECTURE §12 asks for:
- Google Workspace sign-in (OIDC), restricted to the company domain, with 2-step verification enforced there;
- a phone code plus an authenticator code (TOTP) until the domain exists;
- 12-hour sessions.

Phone sign-in alone (ADR 0015) isn't enough for staff, because a SIM swap would open the back office. The brand isn't decided, so there is no company domain or Workspace yet, and both methods have to work. This ADR records the details.

## Decision

1. **Two gates.** A staff sign-in needs both of these:
   - **a proof of identity:** an allowed Google account, or a confirmed authenticator app;
   - **staff status:** an operator must have made the user staff with `python -m app.manage staff add`.

   Staff roles come only from that command, which is audited, and never from Google. Every refusal answers the same `STAFF_ACCOUNT_NOT_ALLOWED`, so nobody can probe who is staff; the reason is logged.
2. **Staff sessions.**
   - Only a staff session carries staff roles; phone sessions never do (ADR 0015).
   - A staff session ends 12 hours after sign-in, however active (ADR 0014). It also stops working at the next request once its user has lost their last staff role.
   - Signing in ends the browser's previous session.
3. **Google sign-in** (`identity/adapters/google_oidc.py`) uses OpenID Connect's authorization code flow with PKCE (S256), `state` and `nonce`. The scope is `openid email` only: no name or photo (DPDP).
   - **Routes:** `GET /v1/auth/staff/google` sends the browser to Google, and Google sends it back to `GET /v1/auth/staff/google/callback`. That redirects to `SITE_URL/staff`, or on failure to `SITE_URL/staff/sign-in?error=CODE`. The codes are `STAFF_ACCOUNT_NOT_ALLOWED`, `STAFF_SIGN_IN_EXPIRED`, `STAFF_SIGN_IN_CANCELLED` and `SERVICE_UNAVAILABLE`.
   - **No server state:**
     - A random login id goes into a 10-minute `__Host-staff-login` cookie. It is HttpOnly and host-only, so no sibling subdomain can plant one.
     - The state, nonce and PKCE verifier are HMACs of that id under `SECRET_KEY`.
     - As a result, only the browser that started a sign-in can finish it, within 10 minutes, and only once.
   - **The code exchange** isn't retried, because a code works only once. An `invalid_grant` answer means starting again. Anything else, such as a wrong client secret or Google being unreachable, answers `SERVICE_UNAVAILABLE` and is logged as an error.
   - **ID token checks.** Google says a token taken straight from its token endpoint can be trusted as it is. It is checked in full anyway, so the adapter stays safe however a token reaches it:
     - **Signature:** RS256 against Google's published keys. Keys are kept for the `max-age` Google sends, at most a day. An unknown key id triggers a new fetch, at most once a minute. Keys already known stay in use while Google can't be reached.
     - **Algorithms and keys:** only RS256 (no `none`, no HMAC algorithms) and keys of at least 2,048 bits.
     - **Claims:** `iss` (`https://accounts.google.com` or `accounts.google.com`), `aud`, `azp`, `exp` and `nonce`.

     This uses the `cryptography` package, now a runtime dependency.
   - **Who may sign in:**
     - `STAFF_GOOGLE_DOMAINS` is matched against the `hd` claim, which Google sets only for accounts a Workspace manages. The address's own domain is never used, since anyone can have an address at a company's domain.
     - `STAFF_GOOGLE_EMAILS` lists exact addresses, for personal Google accounts until a Workspace exists.
     - The address must be verified.
     - With exactly one domain and no addresses, Google's account chooser is narrowed to that domain (`hd`). This is a convenience only, not a check.
   - **Linking:**
     - The first sign-in links the Google account, by its `sub`, to the staff user with the same address. Later sign-ins match the `sub` only, because Google never reuses it, while addresses can change hands.
     - A different Google account arriving with a linked user's address is refused and logged. If that account legitimately replaced the old one, an operator unlinks the old one with `staff remove-google`.
   - **Unconfigured:** without `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, Google sign-in answers `SERVICE_UNAVAILABLE`.
   - **2-step verification:** the Workspace's own policy enforces it, and the ID token can't show it. That is one reason the address allowlist should be temporary.
4. **The fallback: a phone code, then an authenticator code** (`POST /v1/auth/staff/totp`).
   - **The flow:** a staff member signs in by phone, which gives a user session without staff roles. They then send a code from their authenticator app. A right code starts a staff session, which replaces the phone session.
   - **Codes:** TOTP (RFC 6238) with six digits, HMAC-SHA-1 and 30-second steps. A code counts for its own step or one either side, and each step's code works once (`last_used_step`, under a row lock).
   - **Limits:** five tries per staff member per 15 minutes (refused while Redis is down), plus a per-IP limit.
   - **No stored secret:** the app's secret is HMAC-SHA-256(`SECRET_KEY`, salt) cut to 160 bits, and the database keeps only the 16-byte salt. A copy of the database therefore holds no secret, but rotating `SECRET_KEY` means enrolling every app again.
   - **Enrolment from the command line only** (`staff enrol-authenticator`), by someone trusted with the environment, confirmed with the app's first code. Self-enrolment after a phone sign-in would let a SIM swap enrol its own app.
   - **Errors:** a wrong or reused code answers `400 TOTP_INVALID`. Non-staff, and staff without a confirmed app, answer `403 STAFF_ACCOUNT_NOT_ALLOWED`.
5. **Staff-only routes** authenticate first (`401` without a session), then check a policy. A role the session doesn't carry answers `403 FORBIDDEN` (`ForbiddenError`, new); another user's record still answers `404`. The first such route is `GET /v1/admin/staff`, for admins only, which lists staff with their roles and how each one signs in.
6. **Cursor pagination** (`app/core/pagination.py`) applies to every list from now on:
   - Requests take `cursor` and `limit` (default 20, at most 50).
   - Results are ordered by public id. Public ids are UUIDv7, so the cursor is simply the page's last id.
   - Responses are `{items, nextCursor}`, with `nextCursor` null on the last page.
   - A page is one query however many rows it holds; the staff list's test counts the queries.
7. **Operator commands** (`python -m app.manage`, or `make manage args="…"`): `staff add`, `remove`, `list`, `enrol-authenticator`, `remove-authenticator` and `remove-google`. They act directly on the environment's database and write to the audit log as the system (`via: cli`). Staff sign-ins and Google links are audited too.
8. **Settings:**
   - `SITE_URL` and `API_URL`, which must use https when deployed. The redirect URI is `API_URL/v1/auth/staff/google/callback`.
   - The Google client: both values or neither, and only together with an allowlist.
   - `STAFF_GOOGLE_DOMAINS` and `STAFF_GOOGLE_EMAILS`, read in lowercase.
   - Settings errors no longer include the rejected value (`hide_input_in_errors`), since it could be a password in a URL or someone's address.

## Consequences

- **Today:** staff sign in locally with a phone code (from the console sender) and an authenticator app enrolled from the command line.
- **Deployed:** Google sign-in needs the founders to create an OAuth client (type "Web application") in a Google Cloud project, with the redirect URI above, and to set the variables (docs/runbooks/staff-access.md). Once the company domain exists, its Workspace should enforce 2-step verification. When everyone can use Google, the authenticator fallback can be retired with `staff remove-authenticator`.
- **The first admin** is made from the command line; staff can't sign up. Removing someone's last staff role stops their staff sessions at once and removes their authenticator app.
- **The web app** (step 1.6) needs the staff sign-in page at `/staff/sign-in`, which shows the error codes above, and the staff tools at `/staff`.
- **Rotating `SECRET_KEY`** ends Google sign-ins in progress (10 minutes' worth at most) and invalidates every authenticator app.
- **Step 1.4's authorization matrix** builds on `ForbiddenError` and the policy functions. Staff routes multiply from Phase 2 (the ops console).
