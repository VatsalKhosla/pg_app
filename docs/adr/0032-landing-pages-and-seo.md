# ADR 0032: Landing pages and search engines: pages for each campus and locality from live data, structured data without the address, a sitemap from the API, and signed revalidation when a listing changes

- Status: accepted
- Date: 2026-10-28
- Build step: 3.6 (landing pages and SEO)
- Amends: [ADR 0030](0030-pg-page.md), whose cached listing data was fresh within a minute until this step.

## Context

- **BUILD_PLAN 3.6** asks for `/pg-near/[campus]` and `/pg-in/[locality]`, JSON-LD, canonical URLs, a sitemap, robots.txt, dynamic Open Graph images, and revalidation on demand from the API.
- It's done when Google's Rich Results Test validates a PG page and the sitemap lists every published PG.
- **ARCHITECTURE §10.6** asks for landing pages with real inventory, filters and FAQs, and JSON-LD as a `LodgingBusiness` with `Offer` price ranges. The API triggers the revalidation when a listing or its prices change.
- **ADR 0030** renders pages per request with their nonce, from data cached across visitors under the tags `listings` and `listing:<slug>`.
- **The address stays hidden.** The owner's phone and the exact address stay private until a visit or booking (CLAUDE.md rule 11), and so does the exact point (ADR 0021). Search engines must not get them either.

## Decision

1. **Where the PGs are.**
   - `GET /v1/search/places` gives each campus with verified live PGs within search's default 3 km, and each locality with some. Each comes with the count and the month's rent range.
   - It takes one query per kind: for campuses, their points go in as `VALUES` and each reach is found through the display points' index.
   - It feeds the landing pages and their numbers in words, the sitemap and the home page's links.
   - A campus or locality without PGs still has a page. The page says so, is `noindex`, and isn't in the sitemap.
2. **Landing pages** are rendered on the server with no script of their own: the PG card is now a server component that search's list also uses, adding its hover handlers. Each page has:
   - up to 12 PGs, nearest first for a campus and as search recommends for a locality;
   - the count and rent range in words;
   - a way onto the map (`/search?campus=…`, `/search?locality=…`);
   - the localities or campuses nearby that have PGs;
   - four questions, answered from the same live numbers and from the business rules: students pay nothing, and what the field agent checks.

   Every public page has a canonical URL.
3. **Structured data.** Each document is a `<script type="application/ld+json">` with the request's nonce and its "<" escaped.
   - **A PG's page** has a `LodgingBusiness`:
     - its name, description and photos;
     - the locality (`addressLocality`) and the display point (`geo`);
     - the rent range, and the amenities;
     - an `Offer` per room category: the base rent a month, in rupees ("12500.00", written from paise without floating point).

     Never the street address, the exact point or a phone. It also has a `BreadcrumbList` through its locality's page, which its header links to.
   - **Landing pages** have an `ItemList`, a `BreadcrumbList` and an `FAQPage`.
   - **The home page** has an `Organization`, with the app icon as its logo.
4. **The sitemap.**
   - `/sitemap.xml` lists the home page, search, each landing page with PGs, and every listing whose page the public may see.
   - The listings come from `GET /v1/search/sitemap`, 1,000 a page, and are verified ones only while `verified_only` is on, as the listing's page itself decides.
   - Each listing's `lastmod` is when the catalog last said it changed: `search_listings.changed_at`, set by catalog events. The nightly refresh doesn't move it. Until a listing changes, it falls back to when the listing was published.
   - It renders per request from cached data, never at build time, when there's no API to ask.
   - `robots.txt` names it, outside staging.
5. **Open Graph images.**
   - A PG and each landing page have an `opengraph-image`, drawn by `next/og` from the same cached data: the name, the area, the lowest rent, the count.
   - They use the brand's colours. next/og's bundled font has the rupee sign, so no font is added.
   - Links are shared as large cards (`twitter:card`).
6. **Revalidation on demand.**
   - **What's asked.** After each catalog event, the search module first refreshes the listing's entry. Then, in the same transaction, it queues `web.revalidate` with `listing:<slug>` (the slug before and after) and `listings`. A draft nobody can see asks for nothing, and neither does the nightly refresh.
   - **How it's sent.** The worker posts the tags to the web app's `/api/revalidate`, signed with `REVALIDATE_SECRET`, which both share: an HMAC-SHA256 of `<unix time>.<body>`, in hex.
   - **What the web app refuses:**
     - a request more than five minutes off;
     - a bad signature (compared in constant time);
     - tags it doesn't know;
     - a body over 4 KB.
   - **What it does.** It drops the named data at once (`revalidateTag(tag, { expire: 0 })`), so a paused listing isn't served even once more.
   - **Failures.** Any answer but 200 fails the job, which the outbox retries.
   - **Without the secret** (local development) nothing is sent, and caches expire within a minute. Deployed environments refuse to start without it.

## Consequences

- **The Rich Results Test needs a public URL**, so it runs on staging once deployed; Google's tool can't reach a local site.
  - The structured data meets Google's local business requirements (a name and an address), and the browser tests check it.
  - The address is a locality, by design (rule 11), so Google may show fewer details for it.
- **A burst of catalog events** (ops building a listing) asks for a revalidation per event. That's harmless, as each is idempotent.
- **`REVALIDATE_SECRET` must be set in both deployments** and rotated in both together.
- Every campus and locality has a landing page, but only those with PGs are indexed.
