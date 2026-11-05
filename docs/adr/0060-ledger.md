# ADR 0060: The ledger: a module that knows no other, posting in the money event's own transaction, once per event, with the database refusing anything that doesn't balance

- Status: accepted
- Date: 2026-11-05
- Build step: 6.4 (ledger)

## Context

- **BUILD_PLAN 6.4:** a chart of accounts and postings per ARCHITECTURE §9.4 for every money event, in the same transaction; a deferred balance check; an ops ledger view. It's done when a test replays a full booking life cycle and the trial balance is zero.
- **CLAUDE.md:** every money movement writes balanced ledger entries in the same transaction.
- **Bookings and payments both move money,** and already call each other in one direction only (ADR 0056).

## Decision

1. **A `ledger` module knows no other module** (an import-linter contract). Bookings and payments post to it, in their own transactions. It keeps its own copy of the booking's code, so reading the books asks nothing of bookings.
2. **What posts, and when:**
   - **Token received:** as a payment is captured, whatever the booking has come to, because the money came in either way. So the state machine's `RecordTokenReceived` does nothing itself.
   - **Token refunded:** as a refund is processed, not when it's asked for. One that fails or is still with the bank has moved nothing. The gateway's own refund of a payment nobody captured posts nothing, because it never reached the books.
   - **Owner invoiced, and token applied:** as a booking settles (`IssueOwnerInvoice`, `EarnToken`), in the settling change's transaction.

   Each is one pure function, so a CA's change to how an event posts means changing that function and nothing else. Gateway fees, settlement to the bank and the owner's balance come with steps 6.5 and 6.6.
3. **An event posts once.** Each posting has a unique key, such as `token_received:{payment}`. However many jobs, webhooks or retries report the same money, the second answers "already posted".
4. **The database guards the books:**
   - A deferred constraint trigger refuses, at commit, a transaction whose entries don't balance. A posting is also checked in code, so this is the second line.
   - Triggers refuse any update, delete or truncate of transactions and entries, as they do for the audit log. A mistake is corrected by a new posting.
5. **Ops read it,** at `/ops/ledger` (`GET /v1/ops/ledger/trial-balance`, `/transactions`), all of it or one booking's. Nothing in the API writes to it.

## Consequences

- **"Done when."** A test takes a booking from its token to living there, and the balances are exactly §9.4's: the token at the gateway, the rest of the fee owed by the owner, the fee earned and its GST owed. They sum to zero. Other tests cover a refund leaving nothing behind, partial and pending refunds, the same money reported repeatedly, late tokens, and the database's refusals. A property test holds any order of events to zero.
- **The accounting treatment is for the CA to confirm** (founders' guide, section 8).
- **Known edge:** a gateway's refund processed before we've seen its payment captured posts nothing, and the capture posts later, leaving the token on the books. Step 6.6's reconciliation is what catches that.
