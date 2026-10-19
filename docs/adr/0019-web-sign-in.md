# ADR 0019: Signing in on the web, and testing it against the real API

- Status: accepted
- Date: 2026-10-19
- Build step: 1.6 (web auth flows)
- Supersedes: ADR 0012's readonly response types (`--immutable`)

## Context

Steps 1.1 to 1.5 built sign-in, sessions, staff sign-in, consent and data requests in the API. The web app now needs:
- the phone → code → profile flow, with consent;
- a header that knows who is signed in;
- protected pages;
- the staff sign-in page.

The done criterion is that Playwright covers login, logout and protected-route redirects on a phone. Sessions live in the API's cookies (ADR 0014), and the web server renders pages, so the two must agree on who is signed in without the web app re-implementing sessions.

## Decision

1. **The browser talks to the API itself** for everything that changes a session: requesting and checking codes, consent, the profile and signing out (`src/lib/auth/client.ts`, CORS with credentials).
   - **Cookies:** the API sets and clears its own cookies. The web server never writes them; it only checks that the session cookie is there and forwards it (`src/lib/api/server.ts`).
   - **CSRF:** unsafe calls send the CSRF token from its cookie, fetched first if there isn't one. A request refused as `CSRF_TOKEN_INVALID` (the session changed in another tab) is tried once more with a fresh token.
2. **One site.** The browser shares the API's `SameSite=Lax` cookies with the web server only within one site, so the API's URL must be on the same site as the web app:
   - **Locally:** `localhost` for both. The API default was `127.0.0.1`, which made local sign-in impossible from `http://localhost`.
   - **In the browser tests:** `127.0.0.1` for both.
   - **Deployed:** sibling subdomains with `SESSION_COOKIE_DOMAIN`.
3. **Who is signed in, on the server** (`src/lib/auth/session.ts`):
   - `getSession()` asks `GET /v1/me` once per page request (React's `cache`), and not at all without a session cookie.
   - The header uses a version that treats an unreachable API as signed out, so the page reports the trouble instead of the header failing.
   - Protected pages call `requireSession()` or `requireStaff()`. Staff roles come only with a staff session (ADR 0016), so `requireStaff()` also refuses an admin signed in by phone.
4. **Protected areas** are `/account` and `/staff`. The proxy redirects them to their sign-in page when there's no session cookie at all, with `next` set to the page asked for. The page then checks the session itself, since a cookie can be stale.
   - `safeNext()` accepts only a path on this site, never `//host`, `/\host`, another site or a sign-in page, so `?next=` can't become an open redirect.
   - These pages are `noindex`.
5. **The sign-in flow** (`src/components/auth/sign-in-flow.tsx`) runs phone, then code, then consent, then profile.
   - **Consent** is asked only when the API answers `CONSENT_REQUIRED`, and the same code is then sent again with it (ADR 0018). Its boxes are never pre-ticked, and the required one must be ticked to go on.
   - **New people** without a name fill in their profile. **Staff** give their authenticator code instead.
   - **Finishing,** and signing out, load the next page in full. Client-side navigation keeps the root layout, and so the header, as it was rendered.
   - **The resend link** appears once the API allows a new code, without a ticking countdown (CLAUDE.md rule 7).
   - **Forms** use React Hook Form with Zod, as the stack says. The API's field errors (problem+json `errors[]`) show next to their fields. Other failures show our message for the error code, and unknown codes add the request reference.
   - **Zod runs jitless** (`src/lib/forms/zod.ts`). It would otherwise compile validators with `new Function`, and even its probe for whether that's allowed is reported as a CSP violation; the browser tests caught it. A lint rule sends every Zod import through that module.
6. **Turnstile on the web** (`src/components/auth/turnstile.tsx`):
   - The widget renders explicitly, with the page's nonce on Cloudflare's script, which Cloudflare passes on.
   - Its action is `otp_request`, which the API requires (ADR 0015).
   - The CSP's `frame-src` allows `https://challenges.cloudflare.com` only when `NEXT_PUBLIC_TURNSTILE_SITE_KEY` is set.
   - Each try remounts the widget, because a token works once.
   - Without a site key (local and tests) there is no widget, and the API, which has no secret then, accepts any token.
7. **The account page** shows:
   - **The profile:** name, college or workplace, and gender, optional and used only to show the PGs someone can stay in. It is saved with the new `PATCH /v1/me`, which changes only the fields sent; `null` clears one.
   - **Offers:** a toggle for optional offers, as easy to withdraw as to give (DPDP).
   - **Data requests:** asking for a copy of one's data, downloadable when ready, or for the account's deletion (ADR 0018).
   - **Re-consent:** a prompt to agree again when the privacy notice has changed.

   `/privacy` is a placeholder marked DRAFT until step 3.8 writes the notice for a lawyer to review.
8. **Typed client:**
   - The generated types are no longer readonly. openapi-fetch's `Readable<T>`, which removes writeOnly fields from responses, matches arrays with `T extends E[]`, so readonly arrays fall through to its object mapping and turn into objects with an index and every array method. That broke every array in a response type, and there is no fixed release.
   - `unwrap()` now takes its type from the result as it is, rather than inferring it from both branches of the result union, which had added `undefined`.
9. **Browser tests against the real API.**
   - **Setup:** `make e2e` builds the web app pointed at a test API, and Playwright starts that API with `scripts/e2e-api.sh` before the web server.
   - **Isolation:** the API runs on its own database (`platform_e2e`) and Valkey database, migrated on start, with every setting pinned so a developer's `.env` can't change it.
   - **Codes:** the console sender writes sign-in codes to the API's JSON log, where the tests read them.
   - **What runs:** the tests sign up, sign out, sign back in and follow protected-page redirects, on the phone and desktop viewports, with the existing checks (no console errors, no CSP violations, WCAG 2.2 AA).
   - **CI:** the browser job gains uv and Docker, and keeps the API's log if the run fails.

## Consequences

- **Docker:** browser tests need it locally now, as integration tests already did.
- **TanStack Query** isn't used yet: server components and direct calls cover sign-in and the account page. It arrives with the first client-side data fetching (search, Phase 3).
- **Deploying sign-in** needs:
  - the web app and the API on one site, with `SESSION_COOKIE_DOMAIN`;
  - Turnstile's site key on the web and its secret on the API;
  - the SMS provider (ADR 0015);
  - a reviewed privacy notice (ADR 0018).
- **ADR 0012** still holds, apart from the readonly types.
