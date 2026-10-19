# ADR 0005: Outbox jobs instead of a message broker

- Status: accepted
- Date: 2026-10-19 (recorded in step 0.8; decided in the founders' planning, ARCHITECTURE §1 and §3)
- Build step: 0.8 (ADRs and runbook stubs)

## Context

Many changes have side effects that must happen if, and only if, the change commits. A confirmed booking notifies the student; an active booking posts ledger entries and issues an invoice; a stored webhook must be processed. Periodic jobs expire holds, time out confirmations and reconcile payments. A broker such as RabbitMQ, SQS or Kafka can't share a transaction with PostgreSQL, so publishing after commit can lose messages, and publishing before can send them for work that rolled back. A broker is also one more system to run.

## Decision

1. **Jobs are rows in `outbox_jobs`,** written by `enqueue(session, …)` in the caller's own transaction. A job exists exactly when the change that caused it commits.
2. **The worker (`app.worker`)** claims jobs with `SELECT … FOR UPDATE SKIP LOCKED` under a 5-minute lease, so workers never take the same job, and a dead worker's job is taken over.
   - A handler's work and the job's "done" mark commit together.
   - Failures retry with exponential backoff and jitter (10 s doubling to 1 h).
   - After 10 attempts a job is marked `dead` (runbook: dead jobs).
3. **Scheduled work** goes through the same table: each periodic slot is a job with the dedupe key `schedule:<name>:<slot>`, so any number of workers run it once. Every handler and schedule is listed in `app/jobs.py`.
4. **Every handler is idempotent:**
   - Delivery is at least once for external effects.
   - Notifications get dedupe keys per (event, recipient, channel).
   - Webhooks are deduplicated by provider event id.

ADR 0010 records the implementation details from step 0.4.

## Consequences

- No broker to run or pay for, and no lost or phantom messages.
- Throughput is bounded by PostgreSQL, which is ample for the expected load (about 20 writes per second at peak). Polling adds up to a second of latency.
- There is no fan-out publish/subscribe. A domain event that several modules care about becomes one job per consumer.
- Finished jobs are kept for 7 days and dead ones for 30, cleaned up by a scheduled job.
- If a broker is ever needed, `enqueue` stays the interface. A relay could publish committed rows onward without changing callers.
