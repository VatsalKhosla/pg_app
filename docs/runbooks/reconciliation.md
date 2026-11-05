# Reconciliation issues

Reconciliation (ADR 0062) checks our payments against Razorpay every 15 minutes and every morning. What doesn't add up is logged as an error, so it alerts, and waits at **Ops → Reconciliation** (`/ops/reconciliation`) until someone closes it with what they did. An issue is raised once: closing it doesn't make it come back.

## What each issue means, and what to do

| Issue | What happened | What to do |
|---|---|---|
| A payment we have no record of | Razorpay settled a payment that isn't ours: another environment on the same account, or a payment made outside the site. | Find it in Razorpay's dashboard by the reference. If it's a student's or an owner's, talk to them before anything moves. |
| A refund we have no record of | Razorpay took back a refund nobody here asked for. | Find it in the dashboard; a refund from the dashboard itself should also have reached us by webhook. |
| The amounts don't match | The report's amount for one of our payments or refunds isn't ours. | Compare both in the dashboard. Don't change anything here: write down what Razorpay says and ask its support. |
| Settled, but not captured here | Razorpay paid out a payment we still think is waiting. | The 15-minute check usually catches up first. If not, check the booking and the webhook log (webhook-failures.md). |
| Settled, but the refund isn't done here | As above, for a refund. | As above. |
| Something else in the report | A transfer or an adjustment. Transfers come with split settlement in Phase 9. | Read the adjustment's description in the dashboard and close the issue with it. |
| Captured, never settled | A week on, no report has paid a captured payment. | Check the payment's settlement in the dashboard; ask Razorpay's support if it's held. |
| The bank said yes, but it wasn't captured | A payment stayed authorized for over an hour. Razorpay refunds it by itself after 5 days. | Check Razorpay's auto-capture setting. The student may need to pay again. |
| A refund that's stuck | Not taken by Razorpay within an hour, or not sent within a week. | See refunds.md. |
| A payment link paid, but not as asked | An owner paid an invoice's link, but not exactly its balance. | Nothing was marked paid. Check the payment in the dashboard and agree with the owner what happens to it. |

## Closing an issue

Write what you found and what you did, in a sentence someone else can follow later. Closing is audited, and it can't be undone.
