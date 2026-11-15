# ADR 0068: Sign-in by Google and by email code, phone codes off until texts are registered, and every message by email through Gmail

- Status: accepted
- Date: 2026-11-15
- Build step: the founders' batch of 2026-11-12, item 8

## Context

- **Texts can't go yet.** In India a business SMS is a DLT-registered template sent through a registered sender, and that registration isn't done. Until then the site can't send a sign-in code by text, so phone sign-in works only on the test site, which shows the code on screen (ADR 0055).
- **The founders' answer (2026-11-12):** "Continue with Google" for anyone, plus a six-digit code by email. All messages go by email from support@fixyourstay.in through Gmail; the founders have Google Workspace since 2026-11-06. Phone sign-in goes away until the DLT registration is done.
- **An account was its phone.** `users.phone_e164` was required and unique. An address existed only for staff, entered by an operator, and for Google staff sign-in.

## Decision

1. **An account has a phone, an email address or both.**
   - `users.phone_e164` may be null, and the database checks that one of the two is there.
   - Both stay unique. An address is compared without regard to case (citext) and kept in lowercase.
2. **An address on an account is always proven, or entered by staff.** It is one a code was sent to and typed back, one Google says it has verified, or one ops entered for an owner. Nobody types an address into their own profile unproven.
   - So a sign-in that proves an address may enter the account that has it. Without that rule, someone could put another person's address on their own account, wait for that person to sign in, and read what they then add (pre-account takeover).
   - An account keeps its address. Ops can add one to an owner's account that has none, never change one (`EMAIL_TAKEN`).
3. **Email codes work like phone codes**, in the same table and through the same check (`POST /v1/auth/email/request`, then `POST /v1/auth/otp/verify`).
   - A challenge goes to a phone or an address, never both, as the database checks.
   - The limits are the same: Turnstile before sending, 30 seconds between codes, five an hour per address (refused while Redis is down), and five wrong tries.
   - An email code lasts 10 minutes, since mail can be slow to arrive; a text code lasts 5.
   - Answers never say whether an address has an account. A first sign-in needs consent, as before.
4. **Google sign-in is for anyone**, through the staff OAuth client and its callback, so Google needs no new redirect URI.
   - Each kind of sign-in has its own host-only login cookie, and its state, nonce and PKCE verifier are HMACs of a login id of its kind. The callback finishes the one whose state matches. A people sign-in never gives a staff session.
   - Google's account chooser offers any account (no `hd` hint), and only a verified address is used.
   - The Google account is linked to the account with its address on first use (audited), and found by its id afterwards. An address whose account is already linked to a different Google account is refused (`GOOGLE_ACCOUNT_NOT_USABLE`): the address changed hands.
   - Consent travels in the login id: the box on the sign-in page is never ticked for anyone, and ticking it adds it to the link. A first sign-in without it comes back with `?error=CONSENT_REQUIRED` and makes nothing.
   - The page to go back to travels the same way. Only a path on the site is kept, never another site.
   - The link to Google is a link, not a form, because the site's `form-action 'self'` would stop a form's redirect to Google.
5. **Phone sign-in has a switch**, `PHONE_SIGN_IN`, off on the test site and in the browser tests. `GET /v1/auth/methods` says what's on, and the sign-in pages offer only that: Google, then an email code, then a phone number where texts are on.
6. **Every message goes by email to a person with an address**, written from the same wording as its DLT text template, with the brand and the site's address as a signature. Without an address, it goes as a text, which goes nowhere until a provider is chosen.
   - **The mailer:** Gmail's SMTP server (`smtp.gmail.com:587`, STARTTLS) as the Workspace account, with an app password. `MAIL_SENDER` is `smtp`, `console` (local only: the log shows each message) or `unavailable`.
   - **Deployed environments:** they refuse `console`. The test site shows email codes on screen, as it does phone codes, until its mail is set up.
7. **Staff can reach people who have no phone.** Visits, bookings, disputes and the data-request queue show the address too, and checkout fills in the student's address.
8. **The privacy notice is draft-2:** sign-in by email or Google, what Google tells us (the address and an id, nothing else), and Google Workspace among the companies working for us. Everyone is asked to agree again.

## Consequences

- **Gmail's own limits:** about 2,000 messages a day for a Workspace account. That's enough to start with; a transactional mail provider is a paid vendor for the founders to choose later.
- **The app password is a secret like any other:** it's set on the service, never in the repository. It needs 2-Step Verification on the account, and a Workspace admin can turn app passwords off; Google's SMTP relay service is the alternative then.
- **Mail lands in spam without SPF, DKIM and DMARC** on fixyourstay.in. The runbook (staging.md) has the founders' steps.
- **Google sign-in for everyone needs the OAuth client's audience to be External and published.** Until the founders change it, `GOOGLE_SIGN_IN_FOR_EVERYONE=false` keeps the button off the sign-in page. Staff sign-in still checks the Workspace domain, so staff tools stay staff-only.
- **The API's contract widened:** phone fields may be null. Each change is recorded in docs/api-contract-exceptions.md; the web app was changed in the same commit.
- **Turning phone sign-in back on** is one variable once the DLT registration is done. Accounts made by email can then add a phone (a later step: proving a phone on an existing account).
