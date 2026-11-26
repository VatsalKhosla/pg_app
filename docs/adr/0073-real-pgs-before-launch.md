# ADR 0073: fixyourstay.in carries the founders' real PGs before launch: the samples go, a visit comes first, and email waits only for its password

- Status: accepted
- Date: 2026-11-26
- Build step: the founders' request of 2026-11-26, "remove the fictional pg, also make all the testing things launch ready … except for lawyer review pending"

## Context

- **The site at fixyourstay.in is staging** on free plans (ADR 0047). Until launch it serves the main domain, at the founders' request.
- **It was a test copy:**
  - six fictional sample PGs, under a banner on every page saying so (ADR 0047);
  - beds bookable without a visit, paid in test mode (ADR 0058);
  - sign-in codes shown on screen, as no email was set up (ADR 0068).
- **The founders now want it to carry their real PGs.** They're importing the owners they surveyed (ADR 0072). Everything that says "test" should go, except what waits on the lawyer's review.
- **Some of it can't go yet:**
  - production refuses draft legal texts, a missing registration (the tax invoices' GSTIN) and test payment keys (ADR 0034, ADR 0061);
  - the free plan still sleeps when idle.

## Decision

1. **The samples are delisted as the site starts**, unless `SEED_SAMPLES=true` asks for them. The new command `catalog remove-samples` makes ops' own audited move to delisted on every listing named "Fictional Sample PG", and nothing else. Their owners, photos and test bookings stay, as any delisted listing's do. A second run changes nothing, and production may run it (it finds none).
2. **No test-copy banner.** It said the PGs were fictional, which is no longer true. A future test copy with samples (staging, once production takes the main domain) must bring it back with them.
3. **A visit comes first.** `TEST_SITE_REMOTE_BOOKING=false`, so no real owner gets a booking that was paid for in test mode. This is season one's rule everywhere else.
4. **Email waits only for its password.** `render.yaml` now sets `MAIL_SENDER=smtp`, and support@fixyourstay.in as the login and sender. The founders set `SMTP_PASSWORD`, the Workspace account's app password, on the service, and that turns email on.
   - Outside production, an SMTP sender missing its login sends nothing meanwhile (`mail_sender_in_use` is `unavailable`), and the site shows codes on screen as before.
   - Production still refuses to start that way.
5. **No "test" wording in front of people.**
   - The waking note names the brand.
   - The on-screen code says "We can't send codes from this site yet", not "a test copy".
6. **The company's facts, as the founders gave them:**
   - **founders:** Vatsal Khosla and Suryansh Gupta, co-founders, shown with their initials until photos come;
   - **support numbers:** both founders' numbers, answered every day, 9 am to 9 pm;
   - **grievance officer:** Vatsal Khosla.

   The business isn't registered yet, so the pages say the founders run it. The registered name and office stay missing, and a production build waits for them.
7. **The founders' logo** (a teal house in a gold ring) replaces the letter mark everywhere: the header and footer, the favicons, the app icons (with a maskable one for Android) and the pictures social sites show for a link.
   - The founders' file is in `apps/web/src/assets/brand/`.
   - `scripts/brand-logo.py` cuts it out along the ring and makes every size from it.

## Consequences

- **No PG is live** until ops publish the imported ones, once verified and photographed. Search, the home page and the campus pages show their empty states meanwhile, and the smoke test skips a PG's page.
- **Still a test copy underneath:**
  - payments are in Razorpay's test mode, and Turnstile has its test keys;
  - search engines are kept out, and the API sleeps when idle.

  Each goes with the production switch. That waits for the lawyer's review, the registration and GSTIN, live payment keys and a paid host.
- **Until `SMTP_PASSWORD` is set**, anyone can sign in with any email address, because the code is on screen. Owners imported without an address can't be signed in as at all: phone sign-in is off, and only ops add an owner's address.
