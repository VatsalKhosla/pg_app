# ADR 0034: Trust and legal pages: company facts from the founders, legal drafts in the web app with their blanks filled from the policies in force, grievance tickets with their deadlines, and no production build until both are final

- Status: accepted
- Date: 2026-10-29
- Build step: 3.8 (trust and legal pages)

## Context

- **BUILD_PLAN 3.8** asks for these pages, each linked from the footer:
  - About, with the founders' names and faces;
  - Contact, with a phone line a person answers;
  - Pricing, Terms, the Privacy notice, the Refund & Cancellation policy;
  - the grievance officer, with a ticket form;
  - "How your token is protected".

  It's done when the grievance form issues a ticket number. Legal texts are marked DRAFT for lawyer review.
- **Razorpay** checks for these pages before it activates an account (PRODUCT_CONTEXT §7).
- **The Consumer Protection (E-Commerce) Rules, 2020** want the grievance officer's details on the site, complaints acknowledged within 48 hours, and complaints resolved within a month.
- **Facts we don't have.** The founders' names and photos, the registered name and address, the phone line, and the grievance officer are real-world facts. CLAUDE.md forbids inventing them.
- **Policy figures.** The fee rate, the token and the cancellation terms are policies that admins will edit (step 4.1, rules 2, 3, 8 and 9). A page that writes them into its text would drift from what the site does.

## Decision

1. **Company facts** live in one typed file, `apps/web/src/config/company.ts`.
   - Every fact is `null`, or empty, until the founders give it.
   - Until then a page shows a visible placeholder ("[To be added by the founders: …]").
   - That page is `noindex` and stays out of the sitemap (`isIndexable`).
   - The brand stays in `brand.ts` alone.
2. **Legal texts** are versioned Markdown in the web app (`src/content/legal/<locale>/`). The privacy notice was already the web app's, under the API's `PRIVACY_NOTICE_VERSION`.
   - **Versions.** A text is `draft-N` until reviewed, and its page says "DRAFT — needs lawyer review". A browser test checks that the privacy notice's version matches the API's.
   - **Blanks.** Texts carry blanks such as `{brand}`, `{legalName}`, `{token}` and `{freeCancelDays}`. They are filled when the page renders, from the brand, the company facts and the policies in force, so a text can't promise other than what the site does.
   - **Rendering.** The owner agreement's safe Markdown reader is now shared (`src/lib/content/markdown.ts`). It gained links to the site's own paths; any other link shows as written.
   - **Where open questions stay.** Points only a lawyer can settle are written as bracketed questions in the text, not guessed: courts, under-18s and retention periods.
3. **No production build** while a fact is missing or a text is a draft. The root layout calls `assertReadyFor(appEnv)` as it loads, so `next build` fails for `NEXT_PUBLIC_APP_ENV=production`, and other environments show the placeholders.
   - This mirrors the API, which refuses a draft `PRIVACY_NOTICE_VERSION` in production.
   - `next.config.ts` can't import TypeScript modules on Node 20, so the check can't live there.
4. **`GET /v1/policies`** (public, cached five minutes) gives the placement fee (rate, basis, GST rate and mode) and the booking terms (token, hold, free cancellation, check window, confirmation deadline, late-cancel policy).
   - It serves the defaults that step 4.1 will seed into `fee_policies` and `booking_policies`, from `pricing/domain/policies.py`, the first piece of the `pricing` module.
   - Pricing, "How your token is protected" and the Refund policy read their figures from it. The web app caches it under the tag `policies`, for 4.1's revalidation.
5. **Grievances** live in the `compliance` module, as ARCHITECTURE §6 planned.
   - **Filing.** Anyone may complain (`POST /v1/grievances`). Signed out, they give a name and a phone or email, and pass the human check (action `grievance`), with 5 complaints an hour per IP address. Signed in, the account's own phone is the contact, with 10 complaints a day.
   - **Ticket numbers** look like `GR-4M8Q2T7K`: random Crockford codes, like booking codes, so they reveal no count. The core id helpers make both kinds.
   - **Deadlines.** Each grievance stores `acknowledge_by` (48 hours) and `resolve_by` (a calendar month later in India, clamped to the month's end). The database checks the shape of each state.
   - **The queue.** Ops and admins work the queue at `/v1/ops/grievances…`, oldest first, with `late` marking a missed deadline. They acknowledge with a reply, then resolve with what was done; resolving at once acknowledges too. Both are audited.
   - **Texts.** A signed-in complainant is texted on receipt, acknowledgement and resolution, through the outbox and the `Texts` port. A text whose step has passed by the time its job runs isn't sent. A number typed into the form is never texted: anyone could otherwise use us to text anyone.
   - **Their own complaints.** People see their complaints and the replies at `/v1/me/grievances`, on the grievances page. Their complaints are part of their data export.
6. **Web.**
   - Pages under `src/app/(marketing)/`: `/about`, `/contact`, `/pricing`, `/token-protection`, `/terms`, `/privacy`, `/refund-policy` and `/grievances`, the last with the form and the person's own complaints.
   - The ops console has `/ops/grievances`.
   - The footer has two new groups, Company and Policies, beside the main navigation.

## Consequences

- **For the founders:**
  - every fact in `src/config/company.ts`;
  - the lawyer's review of the three texts, and the bracketed questions in them;
  - the DLT templates for the three grievance texts.

  Until then, production can't be built.
- **Retention.** How long grievances and visits are kept joins ADR 0018's list of open retention periods. Until it's decided, they're kept.
- **Step 4.1** replaces the policy defaults with the tables, and revalidates the web app's `policies` tag when an admin changes one.
- **The grievance queue** shows the oldest 50 grievances of a status. Cursor pages come when the volume needs them.
