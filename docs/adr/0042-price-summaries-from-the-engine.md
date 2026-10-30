# ADR 0042: Price summaries from the engine: each month's range from every move-in day's quote, repriced when rules, bands or caps change

- Status: accepted
- Date: 2026-10-30
- Build step: 4.7 (summaries from the engine)

## Context

- **BUILD_PLAN 4.7:** switch `property_price_summaries` to engine output per month, and recompute on `pricing.rules_changed`, allocation changes and band changes.

  It's done when map pins and search budgets match the PG page's prices for the same month. Step 4.6 left the map half of its own done-when to this step (ADR 0041).
- **ARCHITECTURE §18:** precompute the summaries, so search and the map never run the engine per request.
- **What exists:**
  - search keeps a range for each category with a bed to sell, for this month and the next six (ADR 0027). Until now that range was the listed rent at both ends;
  - quotes, the PG page's calendar, and ops' previews and charts build the engine's inputs the same way (ADRs 0039 to 0041).

## Decision

1. **A month's range is what quotes say for its move-ins.**
   - Pricing gives other modules a lookup: for each active room and month, the least and the most a quote made today says for a move-in on any day of that month still to come.
   - It prices an 11-month stay, the one the PG page's calendar prices (`DEFAULT_STAY_MONTHS`, one constant for both). Search's results say so, and that a PG's page prices any dates.
   - Every day is priced, not a sample. A season, an override or an early-bird threshold can change the price on any day, and checking each day needs no knowledge of the rule kinds.
   - The inputs are built as for a quote: the policies in force, the active rule set, the band, the owner's limits and the occupancy. So a month's range holds exactly the prices quotes give.
   - Months past the booking horizon are priced as the editor's preview prices them (ADR 0041).
   - A room whose limits leave no rent gets no range. Search then shows no price for it, and ops are told through the log.
2. **Search keeps those ranges**, in the same table, columns and job (`search.refresh_listing`). Budget filters, price sorting, cards and map pins read them unchanged.
3. **Prices are recomputed when they move:**
   - **A rule set going into force** writes `pricing.rules_changed`. The PG is refreshed with its pages revalidated, so the PG page's cached calendar updates at once rather than within five minutes, as ADR 0040 had it.
   - **A band starting or ending** writes `pricing.band_changed`. Every listing in its locality is repriced (`search.reprice_listing`, one job each), its pages revalidated.
   - **A change to the caps** writes `pricing.caps_changed`. Every listing is refreshed once for that version, and the PG pages follow the `policies` tag that already revalidates.
   - **The nightly refresh** at 00:30 in India still runs, as the day moves early-bird and last-minute thresholds and the current month's days.
   - **Bookings** will move occupancy in Phase 5. That step adds its event, and implements `BedsTaken` for all of these, as for quotes.

   Every event's job has a dedupe key: the rule set, the band and its change, or the caps version.
4. **The occupancy port reaches the jobs.** The job registry gets `BedsTaken` beside its other ports, so search's jobs price with the same occupancy as quotes.

## Consequences

- **"Done when."** An API test publishes a PG with a July peak and an early-bird. Its summaries are then:
  - July at the peak;
  - August from ₹9,500 to ₹10,000: the listed rent until the 12th, then the early-bird;
  - the early-bird every month after.

  A search by budget finds the PG exactly at those limits, and not a rupee past them. The map pins show the same ranges, and every week of the PG page's calendar lies in its month's range, both ends of August among them. Other tests check that a band's start and end reprice its locality, and that a caps change queues one refresh per listing, once.
- **Cost.** Pricing a listing's summaries means up to 31 engine runs per room and month, a few hundred per listing, all in memory. The occupancy port is asked once per run. That's free until Phase 5. Phase 5's `BedsTaken` should then answer for a range of days at once.
- **Step 4.8's alerts** can read clamps and medians from the same lookups.
