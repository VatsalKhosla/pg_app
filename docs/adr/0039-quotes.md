# ADR 0039: Quotes: the engine's answer stored with everything that made it, a 30-minute life, never changed, and occupancy behind a port until booking exists

- Status: accepted
- Date: 2026-10-30
- Build step: 4.4 (quotes API)

## Context

- **BUILD_PLAN 4.4:**
  - `POST /v1/quotes` and `GET /v1/quotes/{id}`;
  - occupancy from real allocations, with holds excluded;
  - a persisted breakdown, a 30-minute expiry, an inputs hash and a human explanation;
  - rate-limited.

  It's done when the quote's numbers equal the engine's for the same inputs, and later steps refuse expired quotes.
- **ARCHITECTURE §8.4:** a booking copies the quote's money fields, and that rent holds for the whole stay. §6 gives `price_quotes`.
- **Rule 7:** the full monthly price, the deposit and the mandatory charges are shown together before booking. **Rule 1:** students pay no fee.
- **What exists:** the engine is pure (ADR 0037), with versioned policies (ADR 0036) and rule sets (ADR 0038). Bookings and their allocations come in Phase 5.

## Decision

1. **One quote is one engine call.** It prices a room category of a PG the public may see (verified-only as the flag says), using:
   - the three policies in force;
   - the PG's active rule set, or none;
   - the band in force for the PG's locality and the category's occupancy;
   - the owner's bounds;
   - the day in India;
   - the occupancy on the move-in.

   The move-in must be from today to the booking policy's horizon (120 days), and the stay 1 to 36 months, or it answers **422 `QUOTE_INVALID`**. A room the public can't see is a 404. Bounds that leave no rent answer **503 `PRICING_CONFIG_ERROR`** and are logged for ops.
2. **Stored with everything that made it** (`price_quotes`). The row holds:
   - the result: the rent, premium, discount, adjustments and clamps, fee, GST, the owner's total, token and what's due at move-in;
   - the category's deposit and mandatory charges as they stood, with their monthly and one-time totals, which the server works out;
   - the explanation;
   - the ids of the rule set, the three policy versions and the band, and `ENGINE_VERSION`;
   - **`inputs_sha256`:** a SHA-256 of a canonical JSON of every input and version, so the same inputs always give the same digest.
3. **Never changed.** A trigger refuses any update of a quote. The rule sets and policies it names never change either (ADRs 0036 and 0038), so a quote stays explainable for as long as it's kept.
4. **30 minutes.** `GET` says `expired` after that. `QuoteService.usable` is how Phase 5's booking takes a quote, answering **409 `QUOTE_EXPIRED`** for an expired one.
5. **What students see:**
   - the rent with its one-line explanation ("Base ₹10,000 · Peak season +15% · Early-bird −5% = ₹11,000/month, fixed for your stay"), with a real minus sign;
   - the adjustments and clamps, the token, what's due at move-in, the deposit, every charge and their totals.

   The owner's fee is stored but not shown: it's the owner's, and students pay none.
6. **Occupancy behind a port.** `BedsTaken` answers how full a category is on a move-in: beds with a secured token or later, and offline tenants, never holds. Booking (Phase 5) will implement it. Until then `NoBookingsYet` says no bed is taken, so occupancy rules wait, and that is honest.
7. **Anyone may quote**; a signed-in student's quote keeps their id. 30 quotes a minute per address. `GET` is open to anyone with the id, since a quote holds no personal data.

## Consequences

- **"Done when."** A test rebuilds the inputs from the database, and the engine gives the same rent, token, rest, fee, GST and digest as the stored quote. After 31 minutes the quote reads as expired and `usable` refuses it. A new version of the rules prices new quotes and leaves the old one as it was.
- **Phase 5** implements `BedsTaken` from allocations, takes quotes through `usable`, and copies their money into bookings.
- **Step 4.5** uses the same engine for the PG page's price calendar, so the page and the quote agree.
- **Retention.** Unbooked quotes past their life can be deleted later; deleting isn't refused, only changing.
