# UI refresh: the brief

Status: the founders own this brief, and its hard rules still bind every change.
- Antigravity built the refresh's steps 1 to 7 on branch `ui-refresh`, and they are live.
- On 2026-11-08 the founders paused Antigravity.
- Claude Code now leads frontend v2 on branch `frontend-v2` (worktree `/home/vatkho32/work/pg-frontend`). Each phase merges to `main` after its checks pass.
- The organised inspiration, the palette options and the type are in `docs/design/inspiration.md`.

## Goal
Make the site look and feel like a top-tier consumer product: confident typography, generous space, considered motion, polished detail on every screen, on phones first. The features, data, flows and URLs stay the same. What changes is the look, layout, type, imagery, motion and finish.

## References
The founders listed these sites. `docs/design/inspiration.md` records what we take from each and what we leave, along with the founders' three attached designs.

| Site (link) | Take | Leave |
|---|---|---|
| https://www.airbnb.co.in/ | Category rail, swipeable card photos, map and list with price pills, sticky reservation card, 1+4 mosaic | Scarcity badges not backed by inventory; fee lines |
| https://www.expedia.co.in/ | Refund status labelled on every result, with a filter; a now-and-later price summary | Member-only prices; "only a few left" banners; review scores we don't have |

## Order of work
Work page by page, so each step can be reviewed and merged on its own:
1. **Design system.**
   - Tokens (colour, type scale, spacing, radius, shadow, motion) go in `apps/web/src/app/globals.css`. Brand colours go in `apps/web/src/config/brand.ts`.
   - The primitives in `apps/web/src/components/ui` (shadcn/ui on Radix).
   - Fonts through `next/font` in `apps/web/src/app/layout.tsx`.
2. **Home:** `src/app/page.tsx`, `src/components/landing`.
3. **Search and the map:** `src/app/search`, `src/components/search`, `src/components/map`.
4. **A PG's page:** `src/app/pg`, `src/components/pg`.
5. **Booking and payment:** `src/app/bookings`, `src/components/bookings`. Read the money rules below first.
6. **Account, visits, sign-in.**
7. **Owner dashboard** (`src/app/owner`) and **ops** (`src/app/ops`). These are working tools, so clarity and density beat flair.

## Hard rules
Tests and review enforce these; breaking one blocks the merge.

### Honest UI
Business rule 7 and the CCPA dark-pattern guidelines.
- **No invented urgency or scarcity.** "Only 2 beds left", "5 people viewing", "price going up" and countdowns appear only when the API returns that fact. The one real countdown is a hold's expiry.
- **The full price, before booking.** The full monthly price, the deposit and mandatory charges are shown together. Nothing is pre-ticked.
- **Money comes from the API.** Prices, fees, tokens, refunds and dues are formatted with `formatINR()`. The browser never computes, rounds or rewords an amount.
- **Founders sign off money wording.** Copy may get clearer, but any change to the meaning of text about money, cancellation, refunds or the token needs their sign-off.

### Brand and words
- The brand name, colours and logo live only in `src/config/brand.ts`. Never type the name into a component.
- Every visible string goes in `apps/web/messages/en-IN.json` (next-intl, typed keys). Translate in server components and pass plain strings to client components.
- **Never invent real-world facts.** No made-up PG names, prices, reviews, testimonials, ratings, "trusted by 10,000 students" counters or partner logos. Use the sample data from `make seed` or clearly marked placeholders.

### Accessibility
WCAG 2.2 AA; axe runs in the component and browser tests.
- Text contrast at least 4.5:1, and 3:1 for large text and UI parts, in light and dark mode. Check text over photos and gradients too.
- Visible focus everywhere, the whole site usable by keyboard, labelled controls, headings in order, one `h1` per page.
- Decorative motion stops under `prefers-reduced-motion`; slowing it down isn't enough. No flashing, and no autoplaying sound.
- Targets at least 24×24 px; 44×44 px for anything thumbs use often.

### Performance
Budgets from ARCHITECTURE §16, measured on a mid-range Android over 4G.
- LCP under 2.5 s, INP under 200 ms and CLS under 0.1. Initial JavaScript under 200 KB gzip on PG pages.
- `make lighthouse` must stay at 90 or above for home. `make lighthouse-pg` and `make lighthouse-search` must stay at 85 or above.
- Server Components by default. Use `"use client"` only for interactive parts, and lazy-load heavy ones (carousels, 3D, animation libraries, the map) where they're used.
- Images go through `next/image` with correct `sizes`; fonts through `next/font`, self-hosted at build time.
- Prefer CSS for motion: transitions, `@starting-style`, scroll-driven animations, View Transitions. A JavaScript animation library (such as Motion) is fine if it earns its weight and loads only where it's used. Say why in the commit.

### Security
The content policy is strict and per request.
- No inline `<script>` and no third-party script or font CDNs. Scripts run only with the request's nonce, and images, fonts and connections are allowed only from our own origins. Bundled npm packages are fine (pinned versions, justified in the commit); remote assets are not.
- No `dangerouslySetInnerHTML` for anything a student, owner or staff member wrote.
- Leave `src/proxy.ts`, `src/lib/security/` and `next.config.ts` headers alone. If a design needs a change there, ask for it.

### Structure
- API calls go only through `src/lib/api` (the typed client). `packages/api-client` is generated: never edit it.
- Map code goes only through the `MapProvider` interface.
- Routes, URLs and search parameters (nuqs) stay as they are, because people share links.
- The browser tests in `apps/web/tests` find things by role, accessible name and visible text. Keep them working, or update the tests in the same commit and say so.

## Hand-over
When a step is ready, commit it on `ui-refresh` and tell the founder what changed and anything you weren't sure about. The founder asks Claude Code to review `ui-refresh`. Claude Code then:
- runs the full checks, the browser tests and the Lighthouse budgets;
- fixes what breaks;
- merges to `main`, which deploys.
