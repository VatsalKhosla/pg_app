---
paths:
  - "apps/web/**"
  - "packages/**"
---

# Frontend rules (apps/web)

- **Read the bundled Next.js docs first.** This Next.js version is newer than most training data: check the guide in `apps/web/node_modules/next/dist/docs/` before using a Next.js API or convention (see `apps/web/AGENTS.md`, which `next dev` maintains).
- **Server Components by default.** Add `"use client"` only for interactive pieces: the map, filters, forms, the booking flow and editors.
- **API access** only through the typed client wrapper in `src/lib/api`. No raw `fetch` to the API and no hand-written API types; regenerate with `make gen-client`.
- **Never compute money in the browser.** Prices, fees, tokens, refunds and "due at move-in" come from the server (quotes, bookings). Format with the shared `formatINR()` helper (`Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })`).
- **Search state lives in the URL** (nuqs), so a shared link reproduces the same results.
- **Forms**: React Hook Form + Zod; show server validation errors from problem+json `errors[]` next to the fields.
- **Honest copy**: no fake urgency, no countdowns except a real hold expiry, and the full monthly price, deposit and mandatory charges together. Strings go in message files (i18n-ready).
- **Accessibility (WCAG 2.2 AA)**: Radix/shadcn primitives, labelled controls, visible focus, keyboard access to the result list and map pins, AA contrast; axe checks in component and E2E tests.
- **Performance**: dynamic-import the map SDK and load it only on the map view; `next/image` with correct `sizes`; `next/font`; no blocking third-party scripts; respect the JS budget in ARCHITECTURE §16.
- **Security**: CSP nonces (no inline scripts without one); only truly public values in `NEXT_PUBLIC_*` (map key restricted by referrer, Razorpay key id); never render owner-supplied HTML.
- **Protected areas**: `/owner`, `/ops` and account routes are `noindex`, with auth checked in middleware **and** again on the server.
- **Brand** name, colours and logo come only from `src/config/brand.ts`.
- **Map** code depends only on the `MapProvider` interface, never on a vendor SDK directly outside its adapter.
