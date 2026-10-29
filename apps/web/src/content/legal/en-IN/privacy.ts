import type { LegalDocument } from "../index";

/** Its version is the one people consent to: the API's PRIVACY_NOTICE_VERSION. */
export const privacy: LegalDocument = {
  version: "draft-1",
  updated: "2026-10-29",
  text: String.raw`
## 1. Who we are

{legalName}, which runs {brand}, decides how your personal data is used: under India's Digital Personal Data Protection Act, 2023, we are the "data fiduciary". Write to us at {supportEmail}, or reach our grievance officer through our [grievances page](/grievances).

## 2. What we collect

- **Your mobile number**, to sign you in with a code and to text you about your visits and complaints.
- **What you tell us**: your name and, if you choose, your email address, where you study or work, and your gender (which decides whether girls', boys' or co-living PGs are shown to you).
- **Your visits**: the PGs, the times you offered, the one booked, and how the visit went.
- **Your complaints**: what you tell our grievance officer, and their replies.
- **Sign-in records**: the IP address and browser you signed in from, to keep your account safe.
- **Your location**, only if you ask for PGs near you: your browser shares it for that search, and we don't keep it with your account.
- **How the site is used**: the kind of searches made (where, and how many filters, never the words typed), the PGs opened, the visits asked for and how they went, and how fast pages load. These go under a random id that lasts only while your browser tab is open and is never your name or number. If your browser asks sites not to track it (Do Not Track or Global Privacy Control), we don't. [Whether this needs your consent is to be confirmed with our lawyer.]

## 3. Why we use it

- **Your account (needed)**: to sign you in, arrange visits and bookings, answer your complaints, keep the site safe from fraud and abuse, and do what the law requires of us.
- **Offers and news (optional)**: messages about PGs and offers, by SMS, WhatsApp or email, only if you choose them when you sign up or later from your [account page](/account). You can withdraw at any time, as easily as you agreed.

## 4. Who sees it

- **The owner of a PG** you visit or reserve, only what's needed to arrange it.
- **Our staff**, only those who need it for their work. Every look at sensitive details is logged.
- **Companies that work for us**: for hosting, text messages, error reports and site analytics (both with phone numbers and other identifying details removed) and, when booking opens, payments. They may use your data only to do that work for us.
- **Authorities**, when the law requires it.

We never sell your personal data.

## 5. Where and how long we keep it

Our database is in India (Mumbai). Some companies that work for us, such as for error reports and site analytics, may handle data elsewhere, as the law allows. We keep your data while your account is open, and then only as long as the law requires:

- sign-in codes, for 7 days;
- sign-in records, for 30 days after the session ends;
- a copy of your data you asked for, for 7 days.

[How long other records are kept is to be confirmed with our lawyer.]

## 6. Your rights

- **See and get a copy** of your data: download it from your [account page](/account).
- **Correct it**: change your details on your account page, or ask us.
- **Delete it**: ask for your account's deletion from your account page. We'll keep only what the law requires us to.
- **Withdraw consent** to optional messages at any time.
- **Nominate someone** to act for you if you can't.
- **Complain**: to our grievance officer first, then, if you're not satisfied, to the Data Protection Board of India.

## 7. Young people

[Whether people under 18 may hold an account, or a parent or guardian must book for them, is to be confirmed with our lawyer.]

## 8. Keeping it safe

Your connection to us is encrypted, sign-in codes are stored only in a form that can't be read back, and staff access is limited and recorded. If a breach puts your data at risk, we'll tell you and the Data Protection Board as the law requires.

## 9. Changes to this notice

When we change this notice, we'll show the new version and date at the top. If we want to use your data for something new, we'll ask you first.
`,
};
