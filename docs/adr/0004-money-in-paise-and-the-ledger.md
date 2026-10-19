# ADR 0004: Money in integer paise, and a double-entry ledger

- Status: accepted
- Date: 2026-10-19 (recorded in step 0.8; decided in the founders' planning, CLAUDE.md rules 10 and 12, ARCHITECTURE §6 and §9)
- Build step: 0.8 (ADRs and runbook stubs)

## Context

The platform moves real money: refundable tokens, owner placement fees with 18% GST (exclusive or inclusive, undecided), refunds, and later rent. Floating-point amounts drift and round unpredictably. Accountants, the founders and the founders' CA must be able to trace every rupee, and owners' money must never pass through the company's own account.

## Decision

1. **Money is integer paise everywhere.**
   - Database: `bigint` columns ending in `_paise`, with `CHECK (>= 0)` unless noted.
   - API: integers in fields ending in `Paise`.
   - Code: plain `int` through `app/core/money.py` (ADR 0010).
   - Rates are integer basis points (`_bps`). Floats are never used for money.
2. **Rounding happens only where a spec says so**, and it is half-up with ties away from zero. Property tests check it against Python's `Decimal`.
3. **The server computes every amount.** Quotes are server-side records, and the web app only displays them, formatting at the edge with `formatINR()`.
4. **Double-entry ledger:**
   - Accounts: `ledger_accounts`, seeded with the chart of accounts in ARCHITECTURE §9.4.
   - Transactions: `ledger_transactions`, each tied to its booking or payment.
   - Entries: `ledger_entries`, each a debit or a credit of a positive amount.
   - A deferred constraint trigger enforces that debits equal credits in each transaction.
   - Every money-moving use case posts its entries in the same database transaction as the state change.
5. **Owners' money is never pooled.** It moves only through the gateway's split settlement (Razorpay Route, Phase 9), never through the company's bank account.
6. **Fees follow `fee_policies`, not constants.** The placement fee is 30% of the listed (base) rent, GST is 18%, and the GST mode is a setting. Dynamic prices never change platform revenue.

## Consequences

- Any amount can be explained from ledger entries, and daily reconciliation compares them with gateway settlements (ARCHITECTURE §9.6).
- A change in accounting treatment, once the CA confirms it, means new transaction kinds or accounts, never edits to posted entries.
- Pricing, booking, payments and the ledger need at least 90% branch coverage plus the property tests named in BUILD_PLAN.md.
- Display formatting (₹, Indian digit grouping) belongs to the web app. The API's `format_inr` is only for text the server writes, such as invoices and messages.
