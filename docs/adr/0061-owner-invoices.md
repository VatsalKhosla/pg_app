# ADR 0061: Owners' invoices: issued as a booking settles, numbered without gaps, kept as issued, and paid through a payment link only the gateway's word marks paid

- Status: accepted
- Date: 2026-11-06
- Build step: 6.5 (owner invoices)

## Context

- **BUILD_PLAN 6.5:** on ACTIVE, the fee, its GST (per `gst_mode`), the token applied and the balance due; sequential numbering per financial year; a PDF; the balance through a Razorpay payment link, paid by webhook. Done when the ₹10,000 example produces an invoice of ₹3,540 with ₹2,000 applied and ₹1,540 due.
- **GST:** an invoice number is at most 16 characters, unique and consecutive within a financial year (CGST Rules, rule 46(b)). `FY2027-28/000123` is 16.
- **Not decided yet:** the company's registered name, address and GSTIN, the service's SAC code, and the CGST/SGST or IGST split by place of supply, which are for the founders and their accountant. Nor what happens to a token larger than the fee, which the product docs don't cover.

## Decision

1. **A module of its own, `invoices`,** which knows neither bookings nor payments (an import-linter contract). Bookings issue an invoice; payments collect its balance. It keeps its own copy of the booking's code, as the ledger does.
2. **Issued in the settling change's own transaction** (the state machine's `IssueOwnerInvoice`), with the fee terms the booking's quote was made under:
   - the year's next serial, from a row locked until the transaction ends, so a change that rolls back gives its number out again and numbers never skip;
   - the posting of what the owner owes, as the fee before GST and the GST, whichever way `gst_mode` worked it out (an inclusive fee is split, not added to);
   - jobs for the PDF, the owner's text and the balance's payment link.
3. **The token pays the fee first.** What's left is the balance. A token larger than the whole fee leaves nothing to pay, and the rest is owed to the owner: posted to `owner_payable` and printed on the invoice, for split settlement to pay (rule 10). How and when that reaches the owner is for the founders to decide.
4. **An invoice stays as issued.** A trigger refuses any change to its number or amounts, and refuses removing one. Only its status, its PDF's key and where its balance can be paid change. The statuses are `issued` and `paid`: `draft` and `void` from ARCHITECTURE §6 wait until the accountant says how corrections work (a credit note, under GST).
5. **The PDF** is made once by a job (ReportLab, BSD licence), put in the private bucket and reached through a link signed for 5 minutes. Until all four of the company's details are set it says "Draft invoice" and that it isn't a tax invoice; production refuses to start without them. The same invoice always makes the same bytes.
6. **The balance through a payment link:**
   - a payment (`purpose = owner_invoice`) is saved first, then a job asks the gateway for the link, its reference (`inv-` and the payment's id) making a retry find the same link;
   - Razorpay sends no message of its own: we text the owner, who pays from their invoices page;
   - only `payment_link.paid`, for exactly the balance, captured, in rupees, captures the payment, posts the money (gateway clearing against what the owner owes) and marks the invoice paid, in one transaction. Anything else paid is an issue for ops (ADR 0062);
   - an expired link is replaced at once; a cancelled or refused one waits for ops to ask for another.
7. **An owner's payment is never a student's.** It's left out of the student's payments and data export, ops can't refund it from the refunds desk, and the gateway's own refund of one posts against what the owner owes, not the student's token.
8. **The test site's bank** pays an owner's own link with a signed `payment_link.paid`, through the real webhook path, with the fake gateway only.

## Consequences

- **"Done when":** a test settles a ₹10,000 room's booking and gets an invoice of ₹3,540 with ₹2,000 applied and ₹1,540 due; the owner pays it at the test bank, the invoice is paid, and the books show nothing owed.
- **Twelve invoices taken at once** get serials 1 to 12, and one taken and rolled back is given out again.
- **For the founders:** the four company details and the GST split; what to do with a token above the fee (below a rent of about ₹5,650 at 30% plus 18% GST); and the Razorpay webhook needs `payment_link.paid`, `payment_link.expired` and `payment_link.cancelled` ticked.
