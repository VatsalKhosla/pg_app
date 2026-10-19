# Runbooks

What to do when something goes wrong in production. Each runbook says how to recognise the problem, how to find the cause, how to fix it safely and how to confirm it's fixed. Most of production (AWS, RDS, Razorpay) arrives in later phases, so these start as stubs. Sections marked **TODO (step x.y)** are filled in by the step that builds the piece they describe.

| Runbook | When |
|---|---|
| [Payment webhook failures](webhook-failures.md) | Payments stuck as pending, bookings not moving after payment, webhook errors or alerts |
| [Dead jobs](dead-jobs.md) | Outbox jobs marked `dead`: a notification, posting or scheduled task stopped retrying |
| [Restoring from a backup](restore-from-backup.md) | Data loss or corruption; also the quarterly restore drill |
| [Staff access](staff-access.md) | Giving or taking away staff access, setting up Google sign-in, failed staff sign-ins |
| [Data requests](data-requests.md) | Export and deletion requests (DPDP), stuck exports, and checking the retention job |

Ground rules for every runbook:
- **Don't make it worse.** Read before you write, and take a snapshot before any manual data change.
- **Write it down.** Note in the incident channel every query run and every change made, with times in IST.
- **Money and personal data:** any manual change to payments, refunds, the ledger or bookings needs both founders, and goes into the audit log, as the app's own actions do.
- **Close the loop.** After an incident, fix the cause in code or alerts, and update the runbook.
