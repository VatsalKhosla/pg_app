# ADR 0041: The pricing editor: any version priced the way a quote is before it's in force, up to a year ahead, beside its band, market and caps, and put in force only once confirmed

- Status: accepted
- Date: 2026-10-30
- Build step: 4.6 (pricing editor, ops first)

## Context

- **BUILD_PLAN 4.6:** a rule list, add and edit forms for each kind of rule, a live preview (a move-in and a stay give the breakdown), a 12-week price chart, the band and the median shown, and activation with confirmation. Owners get the same editor in Phase 7.

  It's done when ops can set a July peak rule and an early-bird rule and see both in the preview, on the calendar and on the map.
- **ARCHITECTURE §8.6:** edit a draft and see its problems (overlapping seasons, a band conflict, caps); preview any move-in and stay with the full breakdown; see a 12-week chart; then activate, which makes an immutable version and is audited. Show the locality's band and the market median next to the inputs.
- **What exists:**
  - rule sets with drafts, problems and activation (ADR 0038);
  - quotes (ADR 0039) and the PG page's price calendar (ADR 0040), which build the engine's inputs the same way.

## Decision

1. **Three reads for ops and admins**, behind the rule sets' policy:
   - **`GET /v1/ops/rule-sets/{id}/preview?room=&moveIn=&stay=`** works for any version (draft, in force or retired). It answers what a quote made today would say were that version in force: the policies and band in force now, that version's rules, and the full breakdown with the owner's fee. Ops may see the fee; students never do. Nothing is stored.
     - Only an active room can be previewed, as only one can be quoted.
     - It answers 422 `QUOTE_INVALID`, in words, for: a move-in in the past or more than a year ahead; a stay outside 1 to 36 months; or a room whose limits leave no rent. A quote answers that last case with 503 and tells ops through the log; the editor tells ops directly.
   - **`GET /v1/ops/rule-sets/{id}/calendar?from=&weeks=12&stay=11`** gives that version's rent for every active room for a move-in each week, up to a year ahead. Each week carries the limits that held it back. Unlike the PG page's calendar, it includes rooms with no free beds: ops price those too.
   - **`GET /v1/ops/properties/{id}/market`** gives, for each active room:
     - its listed rent and the owner's limits;
     - the band in force for its locality and sharing;
     - the median listed rent of the locality's other published PGs for that sharing, and how many room types it comes from. Each active room type counts once. For an even count, the two middle rents are averaged and rounded half-up.

     It also gives the caps in force, which only admins could read before.
2. **The same inputs as a quote.** The quote service builds the engine's inputs once, for quotes, the PG page's calendar, previews and charts. Only the rule set differs: the one in force, or the one asked for. So a preview is what a quote will say once that version is in force. Tests check this both ways:
   - before activation, the version in force previews exactly as today's quote;
   - after activation, the draft's earlier preview equals the new quote;
   - the chart of the version in force equals the PG page's calendar.
3. **A year ahead**, beyond the booking horizon of 120 days. Ops can set up and check next year's season before students can book it, and `bookableFrom` says when students can first quote that move-in. The price is today's answer: early-bird and last-minute count days from today, so a later quote for the same move-in can differ.
4. **The editor**, at `/ops/listings/{id}/pricing`, linked from the listing:
   - its versions;
   - the shown version's rules. A draft's can be added, changed and removed; one that has been in force can't.
   - The forms ask only what each kind needs. They ask which way a season moves the rent, and ask discounts as discounts, so nobody types a minus sign. The API checks every rule again.
   - The draft's problems, in words.
   - Putting the draft in force, behind a confirmation in the page that says what changes and takes an optional note. It's refused while the draft has problems. Discarding is behind its own confirmation.
   - The market, beside the rules.
   - The live preview, asked for again a quarter of a second after the room, the move-in, the stay or the rules change. The last answer stays, dimmed, until the next arrives.
   - The chart, with its stay and first week in the page's address.
5. **The chart** has one small chart per room, so each reads against its own listed rent and band:
   - the rent as steps, since a week's price holds for every move-in that week;
   - the band as a neutral wash, and the listed rent as a hairline;
   - a dot on each week a limit held back;
   - a readout for the pointer and the arrow keys, announced to screen readers, and a table with every value.

   Its colour is the first slot of the dataviz reference palette. The validator passed it, for lightness, chroma and contrast of 3:1 or more, against the app's light and dark backgrounds.
6. **No money is worked out in the browser.** The API returns every rent and amount. The browser turns typed percentages and rupees into basis points and paise exactly, formats amounts, and places the API's rents on the chart's axis.

## Consequences

- **"Done when."**
  - An API test sets a July peak and an early-bird. Previewing next July shows both, and says when students can quote it. Once the version is in force, the PG page's calendar shows July at the peak, then the listed rent, then the early-bird from 30 days ahead.
  - **The map** shows engine prices from step 4.7, which switches its summaries to the engine. That step's test repeats this scenario on the map.
  - A browser test drives the editor end to end: start a draft, add a season, preview it with the owner's fee, read the chart's weeks by table and keyboard, then confirm.
- **Phase 7's owners** get the same endpoints, with a policy that lets an owner reach only their own PGs.
- **Step 4.8's alert**, for a listed rent more than 25% below the median, can use the same market lookup. The median counts room types rather than beds, and is weak with few comparables, so the count is always shown beside it.
