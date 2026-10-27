# ADR 0026: Location privacy and contact hiding: a public read that never loads what it mustn't show, contact details behind sign-in and `hide_owner_contact`, and a sweep over every public route

- Status: accepted
- Date: 2026-10-27
- Build step: 2.7 (location privacy and contact hiding)

## Context

- **Business rule 11:** the owner's phone and the exact address stay hidden until a visit is scheduled or a booking is confirmed. The `hide_owner_contact` flag is on pending legal advice.
  - This defends against leakage (PRODUCT_CONTEXT §6): with the owner's number, a student and an owner can deal directly and skip the fee.
- **ARCHITECTURE §10.5:** the public sees a display point, 80 to 150 m from the building. It is made once and stored (ADR 0021), and public distances are measured from it.
- **BUILD_PLAN 2.7:** public APIs expose only display data. It's done when tests prove that public endpoints never return the exact point, the address line or the owner's phone.
- No public listing endpoint existed yet. Search (3.2), the map (3.3) and the PG page (3.4) will all read listings publicly.

## Decision

1. **The public read is separate from the staff one.** `GET /v1/properties/{slug}` gives a live listing as anyone sees it:
   - the name, description, locality and display point;
   - the gender policy, meals, house rules and whether it's verified;
   - the owner's business name and the amenities;
   - the room categories with a bed to sell, each with its rent, deposit, charges and their totals;
   - the photos and videos that are ready and approved.

   The details:
   - **It never loads what it mustn't show.** `PublicCatalog` reads the display point alone (never the exact one), the owner's business name (never their account) and no address line. A mistake in the response can't leak something that was never read.
   - **Live means** published, and verified as publishing needs it (`verified_only`). A failed or suspended verification hides the listing whatever the flag says. Anything else answers 404, as if it didn't exist.
   - **It's the same for everyone**, so it's cached for a minute (`Cache-Control: public, max-age=60`).
   - **It leaves out** the licence number (a public register would give the address away), the owner's minimum and maximum rents, the listing's status and internal ids.
2. **The contact details** are the owner's phone, the address line and the exact point, from `GET /v1/properties/{slug}/contact`.
   - **Signed in only** (401 otherwise), even with the flag off. That stops anonymous harvesting of owners' numbers, and ties every look to a person.
   - **With `hide_owner_contact` on**, as by default, only someone entitled sees them: a visit scheduled there (step 3.7) or a booking confirmed (Phase 5). Anyone else gets `403 CONTACT_HIDDEN`.
     - The catalog asks through `ContactAccess`, which the visits and bookings modules will answer. Until they exist, nobody is entitled.
   - **Audited every time** (`catalog.contact_shown`, saying whether the person was entitled or the flag was off). This is part of the record that we introduced the student (PRODUCT_CONTEXT §6).
   - **Limited** to 30 looks an hour per person. Requests are let through if Redis is down, so a student on their way to a visit isn't stuck.
3. **Public text can't carry a phone number.** That covers a listing's name, description and house rules, its room categories' labels, its charges' labels, and the owner's business name. A number in any of the forms the logs mask is refused (`LISTING_INVALID`). Staff-only text, such as the address line, isn't checked.
4. **Media:** the public sees only files that are ready and approved, with public links. `MediaRef` now carries the moderation status, so the catalog can tell.
5. **A sweep test** covers every public route.
   - It calls every route the authorization matrix marks as readable by anyone, both anonymously and as a student, plus the contact route.
   - It fails if a response holds the address, the owner's phone, or any point closer than 80 m to the building. A deliberately planted leak was caught.
   - New public routes (search, the map) are swept automatically. A route whose path the sweep can't fill in fails until the sweep is taught.

## Consequences

- Steps 3.2 to 3.4 build on `PublicCatalog` and keep to it: display points only, and distances measured from them (ADR 0021).
- Step 3.7 implements `ContactAccess` for scheduled visits, and Phase 5 for confirmed bookings.
- Owners can't put their number in a listing. Students get it through us once a visit is booked.
- **Founders' decisions:**
  - whether hiding stays, on the lawyer's advice about `hide_owner_contact`;
  - whether, with the flag off, the details should show even to people who aren't signed in.
