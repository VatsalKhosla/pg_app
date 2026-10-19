# Restoring from a backup

All durable data lives in PostgreSQL (ADR 0003): bookings, payments, the ledger and the audit log. Redis holds nothing that exists only there. Object storage (photos, invoices, KYC documents) has its own versioning. Production uses Amazon RDS with automated backups and point-in-time recovery (PITR).

**Stub:** production infrastructure arrives in Phase 8. **TODO (step 8.x)** marks the parts that depend on it: Terraform names, exact console steps, and the targets for how much data may be lost and how long recovery may take (to be agreed with the founders).

## When to use it

- Data was deleted or corrupted (a bad migration, a bug, a manual mistake) and can't be repaired from the audit log or the application.
- The database instance is lost.
- **The quarterly restore drill:** an untested backup isn't a backup. Restore into a scratch instance, run the checks below, and note the time it took.

## Decide first

- **Is a restore the right tool?** A restore rolls back every change made after the chosen moment, including real bookings and payments. Often it's better to restore into a separate instance and copy back only the damaged rows.
- **Pick the moment:** just before the damage, using the deploy log, audit log or error times. Use UTC; RDS expects it.
- **Get both founders' approval** before touching production data.

## Restore (point in time)

1. **Freeze writes:**
   - Put the site in maintenance (**TODO step 8.x:** flag or load balancer rule).
   - Stop the worker, so jobs don't run against a database you're about to replace.
2. **Restore to a new instance.** RDS → the instance → *Restore to point in time*, with the chosen moment, the same instance class and parameter group, and a new identifier such as `<name>-restore-<date>`. RDS never restores over the existing instance.
3. **Check the restored copy** before switching:

   ```sql
   SELECT version_num FROM alembic_version;              -- matches the deployed code's migration head
   SELECT count(*) FROM bookings;                         -- plausible next to the last known numbers
   SELECT max(created_at) FROM audit_logs;                -- just before the chosen moment
   -- The ledger balances: every transaction's debits equal its credits.
   SELECT transaction_id
   FROM ledger_entries
   GROUP BY transaction_id
   HAVING sum(CASE direction WHEN 'debit' THEN amount_paise ELSE -amount_paise END) <> 0;  -- expect no rows
   ```

4. **Switch over:** point `DATABASE_URL` in AWS Secrets Manager at the restored instance, redeploy the API and worker, and leave maintenance.
5. **Reconcile what came after the restore point:**
   - Payments Razorpay saw after the chosen moment aren't in the restored database. Run payment reconciliation and replay webhooks ([Payment webhook failures](webhook-failures.md)).
   - Contact students and owners whose actions were lost.
6. **Keep the old instance** (stopped, with a final snapshot) until the incident is closed, for forensics.

## Confirm

- `make health`'s checks pass against production (**TODO step 8.x:** production health checks).
- Bookings, payments and the ledger reconcile with Razorpay's settlement report for the affected days.
- The incident note records the restore point, how many changes were lost and who was contacted.

**TODO (step 8.x):** automate the drill (restore the latest snapshot into a scratch instance, run the checks, report the duration) and alert when it fails.
