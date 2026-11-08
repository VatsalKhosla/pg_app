# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Students aged 17 to 25**, many from outside Delhi, looking for a safe, verified bed near their college or coaching hub, within budget, without being scammed. They arrive from Google, Instagram and seniors, mostly on a phone.
- **Parents**, who need to be sure the PG is safe and are often the ones who decide and pay.
- **Working professionals** in Gurugram and Noida, with the same needs, outside the student season.
- **PG owners** (typically 10 to 50 beds), who want full beds, better prices in peak season, little admin and on-time payment.
- **Field agents and ops staff**, who verify buildings, run visits and handle bookings, disputes and refunds.

Demand is seasonal: most student demand lands between June and August, peaking around Delhi University's first allocation list in mid-July.

## Product Purpose
An online platform for booking PG (paying guest) beds in Delhi NCR. Students and parents find verified PGs on a map, book a visit, reserve a bed with a small refundable token, and move in. Owners pay a one-time placement fee for each tenant placed; students pay nothing. Success is a student who moves into a room that matches what was shown, having risked very little money to get there.

## Positioning
- **Verified listings:** a field agent visits every building, checks safety and takes the photos.
- **Safe booking:** the student's token is protected until they have moved in and checked the room. Money moves only after move-in plus a 24-hour check window.
- **Owner-side dynamic pricing:** owners earn more in peak season, and all of the rise goes to them.

Students already take big risks with brokers and fake photos. The product makes paying through it visibly safer than paying an owner or broker directly.

## Operating Context
Version 1 is a mobile website that installs as an app (PWA), used on mid-range Android phones over 4G. Parents share a PG's verification report on WhatsApp. Owners and ops staff use the working tools at `/owner`, `/ops`, `/field` and `/admin`.

## Capabilities and Constraints
Business rules live in the repository's `CLAUDE.md` and `docs/PRODUCT_CONTEXT.md`, and every screen obeys them. The ones that shape the interface:
- Students never pay a platform fee.
- The token is ₹2,000 by default, refundable, and counts toward the first month's rent.
- Free cancellation up to 7 days before move-in.
- The full monthly price, deposit and mandatory charges appear together before booking.
- Urgency and scarcity text appears only from real inventory and real rule changes. The only countdown is a real hold's expiry.
- Owner phone and exact address stay hidden until a visit is scheduled or a booking is confirmed.
- All amounts come from the server, formatted with `formatINR()`.
- A strict per-request content security policy: no remote scripts or fonts, images only from our own origins.
- Budgets: home at Lighthouse 90 or above; a PG's page and search at 85 or above; 200 KB gzipped of initial JavaScript at most on PG pages.

Terminology: "PG", "token", "hold", "move-in", "visit", "room type".

## Brand Commitments
- The name, colours and logo live only in `src/config/brand.ts`.
- Copy lives in `messages/en-IN.json`; Hindi is a likely later locale.
- The founders chose the Golden hour palette on 2026-11-08: deep ink, marigold and ivory.
- The founders' references are in `docs/design/inspiration.md`.

## Evidence on Hand
- Live data from the API: listings, campuses, policies and availability.
- Six fictional sample PGs in development (`make seed`). They must stay labelled as samples.
- **There are no real reviews, ratings, testimonials, partner logos, founder photos or student counts yet. Nothing may stand in for them.**
- Listing photos are the field agent's own. Illustrations are labelled as illustrations and never shown as a PG's photos.

## Product Principles
1. **Prove it, don't claim it.** Trust comes from a shown process and real numbers; if a number isn't real, it doesn't appear.
2. **The whole price, every time.** Nobody discovers a cost late.
3. **Parents are in the room.** Everything a student sees should reassure the person paying.
4. **Phones first, on real networks.** Spectacle never costs a slow phone its first screen.
5. **Working tools stay working tools.** Owner and ops screens favour density and clarity over flair.

## Accessibility & Inclusion
WCAG 2.2 AA, with axe in component and browser tests. Full keyboard use, 4.5:1 text contrast and 3:1 for controls, in both themes. Decorative motion and 3D stop entirely under `prefers-reduced-motion`.
