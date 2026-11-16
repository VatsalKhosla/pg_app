# ADR 0071: The owner's overview: beds today, the tenants we placed month by month, our fees, and what waits for the owner

- Status: accepted
- Date: 2026-11-16
- Build step: the founders' request of 2026-11-16 ("owners are very important to us")

## Context

- **The owner's home page was makeshift.** It showed the business details on file, three links and the agreement's version.
- **The founders asked for more.** The first thing an owner sees should show how full their PGs are and what the platform has brought them, in charts.
- **The numbers already existed per PG** (ADR 0063: views, visits, bookings, beds today). Nothing showed the whole business.
- **Money needs care here.** We take the token, and the rest of the first month's rent goes to the owner directly, as does every later month (PRODUCT_CONTEXT). So we know what each stay was booked at, not what the owner was paid.

## Decision

1. **`GET /v1/owner/overview?months=` (3 to 24, default 12)** gives the signed-in owner's whole business. Only their own: the session decides whose, so there is no id to guess. The insights module lines up what each module counts for that owner, as the staff dashboard does:
   - **beds today**, per PG and in all, counted as the per-PG insights count them: a bed is taken if a tenant, a booking, a hold or a block is on it today;
   - **the tenants we placed**: bookings whose student moved in (checked in, settled or finished; a disputed check-in isn't counted until resolved). For each month, how many moved in, and the booked monthly rent of those who lived there on any day of it;
   - **now**: the tenants living there today, and their monthly rent;
   - **all time**: every placed stay's rent for all its booked months; our fees, as invoiced, GST included; and that rent less those fees;
   - **unpaid invoices**, and what's left to pay on them after the token;
   - **what waits**: bookings with the token in that wait for the owner's answer, with the soonest deadline, and visits booked in the next seven days.
2. **Every amount is the server's**, in paise. The page formats them and works out nothing but the bars' widths. The month arithmetic is pure and property-tested.
3. **The words say what the numbers are.** Rent is "booked", never "collected" or "earned", and the page says why. Nothing is estimated, projected or rounded up. An owner with nothing placed yet sees that said plainly, not empty charts.
4. **The page, top to bottom:**
   - what needs the owner, as links straight to it (or a calm "nothing waits");
   - how full the PGs are: a ring for all the beds, with the share in its middle, and a bar for each PG;
   - what we've brought them: four figures and two monthly charts, rent and move-ins, one series each, using the staff dashboard's chart;
   - the way to bookings, PGs and invoices;
   - the business details and the agreement.

## Consequences

- **The query cost is per PG.** Each PG's beds are one layout read and one allocation read. An owner has a handful of PGs; one with hundreds would want a single grouped query.
- **Placement counts follow booking statuses.** A refund after move-in (a resolved dispute) takes the stay out, because its status changes.
- **The chart moved to `components/charts/period-bars.tsx`**, shared by ops and owners. The ring is `components/charts/ring-meter.tsx`.
- **Later, if the founders want it:** rent paid through the platform once it is (PRODUCT_CONTEXT's later step), which would make "collected" honest for those months.
