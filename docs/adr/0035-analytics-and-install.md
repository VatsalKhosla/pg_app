# ADR 0035: Analytics and install: the booking funnel as anonymous, personless PostHog events through our own server, its later steps from the API, web vitals, and an installable site

- Status: accepted
- Date: 2026-10-29
- Build step: 3.9 (analytics and install)

## Context

- **BUILD_PLAN 3.9** asks for:
  - funnel events (search → PG view → visit request → visit done → reservation), PII-masked;
  - PWA installability;
  - web-vitals reporting.

  It's done when the funnel shows in PostHog from a staging run and the site installs on Android Chrome.
- **PostHog** is the analytics tool ARCHITECTURE §3 names. The founders create the account and choose its region (BUILD_PLAN's parallel tasks).
- **Existing pieces.** The web app already had a typed `track()` stub with phone-number masking (ADR 0011), and a manifest.
- **Who records each step.** A funnel needs one id across its steps, but a visit is "done" on the field agent's phone, days after the student asked. The browser can't report that step.
- **Constraints:**
  - The JavaScript budget is 200 KB, and PostHog's browser SDK alone is a large part of it.
  - DPDP: collect the minimum, and nothing that names a person.
  - Owners' and students' phone numbers never leave unmasked.
- **PostHog's capture API**, from its docs and its own libraries' source: `POST /batch/` with `{api_key, batch, sent_at}`. Each event has `uuid`, `event`, `distinct_id`, `timestamp` and `properties`.
  - `$process_person_profile: false` makes an event personless: no person profile, up to 4x cheaper, and funnels still work.
  - `$geoip_disable: true` turns location lookups off.
  - The uuid lets PostHog drop repeats.

## Decision

1. **No PostHog SDK in the browser.** A small transport (`src/lib/analytics-beacon.ts`) queues events and posts them to the site's own `/api/events`, a few seconds later or when the page is hidden. On hiding it uses `sendBeacon`, which survives the page closing.
   - A page's own effects run before the layout's, so its first events can come before the transport starts. `track()` holds up to 20 for it, and drops them if the browser opts out.
2. **An anonymous id per tab**, kept in `sessionStorage`. It ends with the tab and is never tied to an account. A browser that sends Global Privacy Control or Do Not Track gets no id and sends nothing.
3. **`/api/events` passes events on from our server.** PostHog never sees the visitor's IP address. The route:
   - accepts only this site's pages (Fetch Metadata or Origin), up to 16 KB and 20 events;
   - accepts only the funnel's events and `web_vital`, each with at most 12 flat properties, short names and values of 200 characters or less;
   - masks phone numbers again, and makes every event personless with GeoIP off.

   Without `POSTHOG_PROJECT_KEY` and `POSTHOG_HOST`, nothing is collected, and the reporter isn't even mounted.
4. **The funnel's steps:**
   - **`search_performed`**, once per search, when its first page arrives. It reports the kind of area, the campus or locality, how many filters, the sort and the result count. Never the words typed, nor a map area's coordinates, which "near me" centres on the person.
   - **`pg_viewed`**, on a PG's page.
   - **`visit_requested`**, with how many times were offered. The visit request also carries the tab's id (`analyticsId`).
   - **`visit_completed`**, from the API (`app/core/analytics.py`) when the agent records the outcome. It uses the id the student asked with, which the visit keeps as `visits.analytics_id`.

     It goes through the outbox (`analytics.capture`) with its uuid fixed when queued, so a retry counts once. It is sent only if the visit had an id. The worker's `Analytics` port is PostHog's batch endpoint, or nothing without a key.
   - **`bed_reserved`** joins with booking (Phase 5), the same way.
5. **Web vitals.** `next/web-vitals` reports TTFB, FCP, LCP, CLS (in thousandths) and INP as `web_vital` events. Each carries its rating, the navigation type, and the path without its query.
6. **Install.** Chrome's criteria today are a manifest with a name, 192 and 512 px icons, a start URL and a standalone display, over HTTPS; no service worker is required. The existing manifest meets them.
   - A browser test asks Chromium itself (DevTools `Page.getInstallabilityErrors`) and expects nothing in the way.
   - A service worker would only add a cache that could serve stale prices, so there isn't one.
7. **Proof without the founders' account.** A stand-in PostHog (`tests/e2e/fake-posthog.mjs`) receives everything in the browser tests. The visit test checks one anonymous journey arrives in order (search, PG view, visit request, visit done), personless and without the student's name.

## Consequences

- **For the founders:**
  - the PostHog account and its region (EU defaults to discarding IP data), and the project's settings;
  - a staging run that shows the funnel there;
  - installing on an Android phone;
  - whether these anonymous analytics need consent. The privacy draft describes them and asks the lawyer.
- **Linked records.** The visit's `analytics_id` links an anonymous journey to a visit in our database. It's part of the person's data export, and it goes when the visit does.
- **More events later.** A new funnel step needs its name added to `ANALYTICS_EVENTS`, which `/api/events` accepts from, and a call site.
