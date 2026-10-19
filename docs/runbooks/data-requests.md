# Data requests

Under the DPDP Act, people can ask for a copy of their personal data or for their account's deletion (ADR 0018). Exports run by themselves. Deletions wait for the team. Only a signed-in person can ask, so a request always comes from the account's own phone.

## Where requests show up

- **The queue:** `GET /v1/ops/data-requests?status=received`, from an ops or admin staff session. The ops console (Phase 2) will show the same list. Each request has its kind, its time, and whose it is (phone and name).
- **Everything:** leave out `status` to see every request, resolved ones included.

## Exports

- **Normal case:** the worker builds the file within minutes. The person downloads it for 7 days, then the retention job deletes it.
- **Stuck exports:** if a request stays `received` for more than an hour, check that the worker is running. Then look for a dead `compliance.build_export` job ([dead jobs](dead-jobs.md)). Once the cause is fixed, retry the job as that runbook says.
- **Nobody else's file:** staff can't download someone's export, on purpose. If a person can't download theirs, check the request is `ready` and hasn't expired; they can simply ask again.

## Deletions

**What a deletion erases, and what the law makes the platform keep, isn't decided yet.** Invoices, payments, disputes and the audit log have retention duties. The founders decide with legal advice, and the app then does the erasure. Until then:

1. Don't delete anything by hand in the database.
2. Call the person on the phone in the request. Confirm they want their account deleted, and explain what has to be kept and why.
3. Resolve the request with what was done or why it can't be done yet. The person sees the note in their list of requests.

   ```http
   POST /v1/ops/data-requests/{id}/resolve
   {"outcome": "rejected", "note": "…"}
   ```

   Use `completed` only once the erasure has really been carried out.

Resolving is recorded in the audit log (`data_request.resolved`), with who did it. A resolved request can't be resolved again; the person can ask again.

**Response time:** answer every request promptly. The legal deadline is for the founders' lawyer to confirm, and this runbook should record it.

## Retention

- **When:** the retention job runs daily at 03:30 India time.
- **What it deletes:** sessions 30 days after they end, sign-in codes after 7 days, export files after 7 days. The full schedule is `RETENTION_RULES` in `apps/api/src/app/jobs.py`.
- **Checking a run:** each run leaves an audit entry (`retention.ran`) with how many records each rule removed. A day without one means the job didn't run: check the worker and the scheduler.
