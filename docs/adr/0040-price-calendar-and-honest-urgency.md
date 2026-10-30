# ADR 0040: The price calendar and honest urgency: every price and claim on the PG page from the quote engine and real inventory, and nothing else

- Status: accepted
- Date: 2026-10-30
- Build step: 4.5 (price calendar and honest urgency)

## Context

- **BUILD_PLAN 4.5:**
  - a calendar endpoint (weekly move-ins, 12 weeks, cached) and its UI on the PG page ("Move in by 15 Jun: ₹9,500 · from 1 Jul: ₹11,000");
  - "only N beds left" only from real availability, with N at most 3;
  - a "price fixed for your whole stay" badge;
  - quotes that show the full breakdown.

  It's done when tests prove every urgency message is backed by data, and the PG page shows quote-consistent prices.
- **Rule 7:** urgency and scarcity text only from real inventory and real rule changes; countdowns only for a real hold expiry; the full monthly price, deposit and charges shown before booking.
- **ARCHITECTURE §8.5:** a calendar cached five minutes; "price rises on 1 Jul" is allowed only because the calendar proves it.
- **What exists:** quotes (ADR 0039) run the engine. Until now the PG page showed the listed rent.

## Decision

1. **`GET /v1/properties/{slug}/price-calendar`** (public, `Cache-Control: public, max-age=300`, 60 a minute per address). For each active room category with beds, it gives:
   - the rent for a move-in each week from `from` (today at the earliest), 12 weeks by default, up to the booking horizon, for a `stay`-month stay (11 by default, the common one);
   - its free beds.

   Each week's rent is what a quote for that move-in would say: the quote service builds both from the same inputs (the policies, the rule set, the bands, the occupancy) and runs the same engine. A room the bounds can't price shows no weeks, and is logged for ops.
2. **The PG page reads only the calendar.** For each room:
   - **headline:** the soonest week's rent, "moving in this week, for an 11-month stay", with the "Price fixed for your whole stay" badge;
   - **price changes:** "Move in by …: ₹A · from …: ₹B", only where consecutive weeks' prices differ in the calendar. The browser groups weeks the API priced; it works out no price;
   - **scarcity:** "Only N beds left", only when the calendar's free beds are 1 to 3.

   The page's structured data for search engines uses the same rents. If the calendar can't be fetched, the listed rents show and no claim is made.
3. **"Check your price"**: a room, a move-in date (today or later) and a stay, which asks for a quote. It shows:
   - the rent "fixed for your whole stay" and the API's explanation line;
   - the token and that it counts toward the first month;
   - what's due at move-in, the deposit and the other charges' totals;
   - when the quote stops holding.

   It says reserving opens soon, as booking is Phase 5. No timer counts down.
4. **Free beds** are active beds less those booked, once booking exists (Phase 5). Until then no bed is booked, so free beds are the category's active beds. That's real inventory, not invented.

## Consequences

- **"Done when"**:
  - an API test proves each calendar week equals a quote for that move-in, including a season that starts partway through the 12 weeks;
  - unit tests prove price changes come only from the calendar's changes and scarcity only from 1 to 3 free beds;
  - a browser test proves the PG page's rents, badge, change line and "only N left" are exactly the calendar's, and that the checker's price is a quote's.
- **The calendar is cached** in the web app under the listing's tags and `policies`, so a listing or policy change shows at once (ADR 0032, 0036). An activated rule set waits for the five-minute cache unless the listing changes too. (Since ADR 0042, activating a rule set revalidates the PG's pages at once.)
- **Phase 5** makes free beds and occupancy count bookings, through the same calendar.
