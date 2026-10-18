# ADR 0011: Web foundations

- Status: accepted
- Date: 2026-10-19
- Build step: 0.5 (web skeleton)

## Context

Every later web feature (the map, search, the booking flow) builds on the same layer: security headers, translations, error reporting, the layout and the performance budget (ARCHITECTURE §16: initial JS under 200 KB gzip on PG pages, LCP under 2.5 s on a mid-range phone). Next.js 16 changes several conventions from the versions most examples describe: `middleware.ts` is now `src/proxy.ts`, error boundaries get `retry`, and Turbopack is the default bundler. This ADR records the choices.

## Decision

1. **A strict, per-request Content Security Policy.** `src/proxy.ts` makes a 128-bit nonce for every page request and sends the policy. Next.js puts the nonce on its own scripts.
   - Scripts: `'self' 'nonce-…' 'strict-dynamic'`, with no `'unsafe-inline'` (ARCHITECTURE §17). `'unsafe-eval'` appears only under `next dev`, for React's debugging.
   - Styles allow `'unsafe-inline'`. Radix's scroll lock, Google Maps (step 3.5) and server-rendered `style` attributes can't carry a nonce. Injected CSS also can't reach other sites: images, fonts and connections are limited to this site, the API and (when on) Sentry.
   - `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'` and `form-action 'self'`. `upgrade-insecure-requests` applies on HTTPS only.
   - With a Sentry DSN, violations are reported to Sentry's security endpoint (`report-uri` plus `report-to`/`Reporting-Endpoints`).
   - The other headers are static, set in `next.config.ts`: HSTS, nosniff, `X-Frame-Options: DENY`, Referrer-Policy, COOP, and a Permissions-Policy that allows only geolocation, and only on this site.
2. **Pages render per request.** A nonce must be new on every response, so the root layout calls `connection()`. ISR and CDN caching of HTML are off for now. Step 3.4 (ISR PG pages) revisits this. Its options are Next's experimental hash-based CSP (SRI), or nonces on dynamic routes only.
3. **Translations: next-intl with one locale, `en-IN`**, and no locale in the URL yet. That locale also gives Indian digit grouping.
   - Messages live in `messages/en-IN.json` and are typed: an unknown key fails `tsc`. Times are shown in Asia/Kolkata.
   - **The browser ships no message formatter.** Server components translate. Client components get plain strings as props, and the error page gets them through a small context the root layout fills. This keeps next-intl's client runtime (about 13 KB gzip) off every page.
   - When a client component needs client-side formatting (form errors with arguments, say), it gets a scoped `NextIntlClientProvider`.
   - next-intl's experimental build-time precompilation was not adopted. It would also rewrite the message file that `global-error.tsx` reads directly.
4. **Code that most visitors don't use loads on demand.** The phone menu's dialog (Radix, about 27 KB gzip) loads the first time someone reaches for the menu button: on hover, press or focus. Sentry's SDK loads only when a DSN is set.
   - The home page now ships about 151 KB gzip of JavaScript, of which about 130 KB is React and Next.js themselves.
   - Next.js's default browser targets (Chrome/Edge 111+, Firefox 111+, Safari 16.4+) match what Tailwind CSS 4 requires, so no browserslist override is needed.
5. **UI kit:** Tailwind CSS 4 and shadcn/ui components, copied into `src/components/ui` and built on the single `radix-ui` package.
   - Colours come from `src/config/brand.ts` as CSS custom properties, with dark-mode values. Each colour pair meets WCAG AA contrast.
   - Inter is self-hosted by `next/font` (no request to Google from the browser). App icons are generated from `brand.ts` at build time.
6. **Monitoring and analytics are wired but off.**
   - **Sentry:** Browser reporting needs `NEXT_PUBLIC_SENTRY_DSN`; server reporting needs `SENTRY_DSN`, read at start-up. Both send errors only, with Sentry 11's `dataCollection` turned off for user info, cookies, headers, bodies, query strings and local variables (DPDP: collect the minimum). Phone numbers are masked with the same pattern as the API. Source-map upload (`withSentryConfig`) waits until a Sentry project exists.
   - **Analytics:** `src/lib/analytics.ts` types the booking funnel's events and drops them until PostHog arrives (step 3.9).
7. **Tests:**
   - **Vitest:** jsdom with Testing Library and axe for components; the node environment for the proxy, CSP and PII code. `make test-web` is part of `make check`.
   - **Playwright:** a production build on a phone and a desktop viewport (`make e2e`). Every test fails on console errors, uncaught exceptions and CSP violations. Pages are scanned with axe for WCAG 2.2 AA in light and dark mode.
   - **Lighthouse:** `make lighthouse` runs the mobile audit three times, each in a fresh browser, and fails if a category's median is below 90. A reused browser made later runs measurably slower.
8. **This machine (glibc 2.28) runs webpack.** `scripts/next-bundler-flag.sh` picks `--webpack` where Turbopack's native binary can't load, for `make dev`, `make web-build`, `make e2e` and `make lighthouse`. CI and Vercel use Turbopack. Chromium started outside Playwright needs `--password-store=basic` there, or every page load hangs on the missing desktop keyring.

## Consequences

- HTML can't be cached at the edge until step 3.4 decides between hashes and dynamic-only nonces. Server render time is part of every page view, so time to first byte must be watched (it is about 30 ms locally).
- Interactive features must keep their JavaScript lazy where they can. React and Next.js already use about 130 KB of the 200 KB budget for PG pages.
- Inline styles stay allowed. If a policy without them is ever needed, Radix's style injection can take a nonce through `get-nonce`, and Maps needs its own review.
- The first open of the phone menu waits for a small chunk, which is fetched on hover, press or focus to hide most of that wait.
