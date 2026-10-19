# Payment webhook failures

Razorpay tells us about payments through webhooks (`POST /v1/webhooks/razorpay`). The API checks the signature on the raw body, stores the event in `payment_events` (unique per provider event id), queues it for the worker and answers 200 within a second. The worker moves payments and bookings forward (ARCHITECTURE §9.3). Only a verified webhook or a server-side fetch moves a booking, never the browser.

**Stub:** payments arrive in Phase 6. **TODO (step 6.x)** marks the details that depend on that code.

## Recognise it

- A student paid, but their booking stays HELD or expires. Ops sees a payment in Razorpay's dashboard that our ops console doesn't show.
- Razorpay's dashboard shows failed webhook deliveries (non-2xx responses or timeouts). After repeated failures, Razorpay may disable the webhook.
- Logs show webhook signature failures, or `payment_events` rows that were never processed.
- **TODO (step 6.x):** alerts on signature failures, on events unprocessed after 5 minutes, and on payments stuck in created/authorized.

## Find the cause

```sql
-- Events that failed verification (wrong secret, or not from Razorpay)
SELECT provider_event_id, event_type, received_at
FROM payment_events
WHERE signature_valid = false AND received_at > now() - interval '1 day'
ORDER BY received_at DESC;

-- Verified events the worker hasn't processed, or failed on
SELECT provider_event_id, event_type, received_at, processed_at, error
FROM payment_events
WHERE signature_valid AND (processed_at IS NULL OR error IS NOT NULL)
ORDER BY received_at;
```

| What you see | Likely cause | Next step |
|---|---|---|
| Every event fails verification | The webhook secret was rotated in Razorpay but not in our secrets, or the reverse | Make them match (below) |
| Razorpay shows timeouts | The API was down or slow | Check API health, then replay from Razorpay |
| Events stored but not processed | The worker is down, or the `process_payment_event` job is dead | Check the worker; see [Dead jobs](dead-jobs.md) |
| Processed with an error | Unexpected event shape, or a state the booking can't move from | Read the error and the booking's `booking_events`; fix the code |
| Nothing arrives at all | The webhook is disabled or points at the wrong URL | Check the webhook settings in the Razorpay dashboard |

## Fix it

1. **Secret mismatch:** update the webhook secret in AWS Secrets Manager to match Razorpay's dashboard, or rotate both together, then restart the API so it reads the new secret. Never paste secrets into tickets or chat.
2. **Missed events:** replay them from Razorpay's dashboard, or wait for the reconciliation job. It fetches payments stuck in created/authorized every 15 minutes, and does what the missed webhook would have done. Both paths are idempotent, so duplicate deliveries are harmless.
3. **Stuck processing:** fix the cause, then requeue the dead `process_payment_event` jobs ([Dead jobs](dead-jobs.md)).
4. **A booking that missed its hold because the webhook came late:** the worker revives it if the bed is still free (`late_payment_revive`). Otherwise it refunds automatically and tells the student (ARCHITECTURE §7.4). Check that this happened; refund by hand only through the ops console, with both founders' approval for amounts above the configured limit.

**TODO (step 6.x):** exact Razorpay dashboard paths, event names and the ops-console replay screen.

## Confirm

- New events arrive with `signature_valid = true` and get `processed_at` within a minute.
- The affected payments and bookings show the right status, and the ledger balances (`make` target TBD in step 6.x).
- Razorpay's dashboard shows successful deliveries again.
