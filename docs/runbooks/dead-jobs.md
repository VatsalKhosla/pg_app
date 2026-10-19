# Dead jobs

Background work (notifications, ledger postings, webhook processing, scheduled tasks) runs as outbox jobs (ADR 0005). A job that fails `max_attempts` times (10 by default) stops retrying and is marked `dead`. A job of an unknown kind is marked `dead` at once. Nothing retries a dead job on its own.

## Recognise it

- The worker logs `outbox job dead` at error level, with the job id, kind and the masked error.
- The metric for dead jobs rises. **TODO (step 8.x):** alert on any new dead job.
- Symptoms depend on the kind: a missing SMS, a booking whose invoice never appeared, a scheduled cleanup that stopped.

## Find the cause

Connect to the database with a read-only role, then list recent dead jobs:

```sql
SELECT id, kind, attempts, max_attempts, run_at, updated_at, last_error, dedupe_key
FROM outbox_jobs
WHERE status = 'dead'
ORDER BY updated_at DESC
LIMIT 50;
```

Group them, to see whether one cause killed many:

```sql
SELECT kind, left(last_error, 120) AS error, count(*)
FROM outbox_jobs
WHERE status = 'dead' AND updated_at > now() - interval '1 day'
GROUP BY 1, 2
ORDER BY 3 DESC;
```

`last_error` is capped at 2,000 characters and has phone numbers masked. The request id and the full traceback are in the worker's logs and in Sentry around `updated_at`.

Typical causes:
- **A bug in the handler:** the same error on every job of the kind.
- **A provider outage or a revoked credential:** network or 401 errors from SMS, email or Razorpay.
- **Bad data:** one payload that can never succeed.
- **No handler registered:** `no handler is registered for this kind`. A deploy removed or renamed a handler while jobs of the old kind were queued.

## Fix it

1. **Fix the cause first:** deploy the code fix, or restore the credential. Requeuing before that only makes more dead jobs.
2. **Requeue the affected jobs.** Handlers are idempotent, so running a job again is safe even if part of its work happened (ADR 0005). Requeue by id or by kind and time window, never all dead jobs blindly:

   ```sql
   BEGIN;
   UPDATE outbox_jobs
   SET status = 'pending', attempts = 0, run_at = now(),
       locked_by = NULL, locked_until = NULL
   WHERE status = 'dead'
     AND kind = 'notifications.send_sms'          -- the affected kind
     AND updated_at > '2027-07-14 10:00+05:30'    -- the incident window
   RETURNING id;
   -- Check the count matches what you expected, then:
   COMMIT;
   ```

   Keep `last_error` for the record; the next failure overwrites it.
3. **Jobs that should never run again** (for example, a reminder whose moment has passed) stay `dead`. Write down why. Dead jobs are deleted after 30 days.

**TODO (step 8.x):** an ops-console screen and a `make` target for listing and requeuing dead jobs, with an audit log entry, so this rarely needs SQL.

## Confirm

- The requeued jobs move to `done` (`SELECT status, count(*) FROM outbox_jobs WHERE id = ANY(:ids) GROUP BY 1`).
- The symptom is gone: the SMS arrived, or the invoice exists.
- No new dead jobs of that kind in the next hour.
