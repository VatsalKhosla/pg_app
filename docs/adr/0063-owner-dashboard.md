# ADR 0063: The owner dashboard: ops' own tools, scoped to an owner's PGs by one check, with a 404 for anyone else's

- Status: accepted
- Date: 2026-11-06
- Build steps: 7.1 to 7.6 (owner dashboard)

## Context

- **BUILD_PLAN Phase 7:** onboarding with licence and society-permission uploads; a per-bed calendar with blocks; a bookings inbox with reminders; the pricing editor for owners; invoices; and insights. Done when an owner can run their PG's bookings and pricing from a phone without calling ops.
- **Ops already had the tools:** the bed calendar and blocks (ADR 0044), the pricing editor (ADR 0041), confirm and reject (ADR 0048). Owners need the same, for their own PGs only.

## Decision

1. **The same services, under `/v1/owner/...`, with one ownership check each.** An owner's route resolves the PG from whatever it names (a PG, a bed, a block, a rule set or a rule) and answers 404 unless it's the signed-in owner's. No second copy of the rules: caps, bands and the clamp (rule 6), the price lock (rule 5) and the exclusion constraint on beds apply to owners exactly as to ops. The authorization matrix holds every route to it.
2. **The audit log names owners as owners.** Actions in pricing and inventory are recorded as `owner` when an owner takes them, rather than as staff.
3. **The web app reuses ops' bed calendar and pricing editor.** A small context tells them whom they serve, and their calls go to the matching routes; the ops pages are unchanged.
4. **Documents (7.1):** an owner uploads a licence or society permission as a private document (the media pipeline's checks and private bucket), attaches it to their PG, and ops accept or refuse it once, with a note the owner sees. What the law requires of a PG stays for the founders and their lawyer.
5. **The inbox (7.3):** the owner's bookings newest first, by status, with each one's deadline; a text reminds the owner once, three hours before a booking's deadline; and the visits booked to their PGs in the next two weeks, with each student's first name only.
6. **Insights (7.6):** page views, visits asked for, bookings made, how full the PG is today, and each room's listed rent beside the middle of its locality's. A PG's page counts its views from the browser, once a session, into one row a PG a day (rate-limited, behind the CSRF check like any other post). Ratios are whole basis points, and none is shown where there's nothing to divide by.
7. **Invoices (7.5)** were built with step 6.5 (ADR 0061).

## Consequences

- Tests take an owner through their own PGs, beds, pricing, documents, inbox and numbers, and hold every other PG to a 404.
- Insights count our own records, so they start from zero on a PG listed today. Views before this step weren't counted.
