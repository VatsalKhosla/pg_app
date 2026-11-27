# ADR 0072: Owners and their PGs from a filled-in template: checked first, then made as drafts through the console's own services

- Status: accepted
- Date: 2026-11-22
- Build step: the founders' owner survey (2026-11-22)

## Context

- **The survey comes as a spreadsheet.** The founders gather PG owners through a survey, exported as a spreadsheet of free-text answers ("Single 8000, Double sharing 5000 per person"), and asked for its owners and PGs to be put on the site.
- **Every listing was typed by hand**, form by form, in the ops console. Nothing read a file.
- **The repository is public and the answers are personal**: names, phone numbers, addresses. They can't go into code, fixtures or commits.
- **Nobody outside ops writes to the live database**, and the free-plan test site has no shell for an operator command.

## Decision

1. **A template, not the survey.** The import reads a fixed template, one row per room type. Rows with the same owner phone and PG name are one PG. The template uses the console's words:
   - room types: `single`, `double`, `triple`, `quad`;
   - rent and deposit in whole rupees;
   - amenities by their slugs;
   - lists separated by `;`.

   It reads the template however it arrives (2026-11-27): saved as CSV, copied from a spreadsheet or a table view (tab-separated), or exported with semicolons; with the header row below a title, and its names written as people write them ("Owner Name"). Columns the template doesn't have are left out.

   Free-text survey answers are turned into rows by a person, who decides what a range like "₹18,000 to 22,000" means for the listed rent (CLAUDE.md rule 2 makes it the fee's basis). The parser refuses anything it would have to guess. The template comes from `/ops/listings/import/template`, with a fictional example.
2. **Check, then import, in the ops console** (`/ops/listings/import`, `POST /v1/ops/listing-imports`, ops only). Personal data goes from the person's file to the API and nowhere else, and is never logged.
   - A check (`dryRun`, the default) reads every row, asks the database what already exists and what it doesn't know (a locality, an amenity), and makes nothing.
   - An import goes PG by PG. A failure leaves the other PGs be.
3. **Only through the existing services**: adding an owner, creating a listing, adding room types, setting amenities. Every rule the console keeps (texts, rents and their bands, labels) holds for a file too.
4. **What gets made:**
   - **owners:** added, or found by their phone; the email, when given, is added only if the account has none (ADR 0068);
   - **listings:** always drafts, with the location marked approximate (the owner's own pin, unchecked);
   - **a PG without a latitude and longitude:** only its owner is added, and the PG is reported as "needs a pin", for ops to add from New listing;
   - **running a file again** finds the owners by phone and the PGs by name, and makes nothing twice.
5. **Nothing is published by an import.** Verification, photos and the decision to go live stay with ops, as for any listing.

## Consequences

- **Messy answers need a person in between.** Turning survey answers into rows takes a person: a range, a missing rent or a map link that names a different PG gets their judgement, not the parser's.
- **Places come first.** A new area must first be added from OpenStreetMap (docs/runbooks/geo-data.md) before its PGs can be imported. Shahbad Daulatpur and Delhi Technological University were added for the survey's first owners.
- **Files are capped** at 200 rows and 200,000 characters: a day's onboarding, not a migration.
