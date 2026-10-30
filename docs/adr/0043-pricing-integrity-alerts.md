# ADR 0043: Pricing's integrity alerts: a rent far below its market, a week of quotes often held back, rules that keep changing; each raised once, and resolved by ops or by the check

- Status: accepted
- Date: 2026-10-30
- Build step: 4.8 (integrity alerts)

## Context

- **BUILD_PLAN 4.8:** ops alerts when a listed rent is more than 25% below the locality median, when clamps fire on more than 20% of a property's weekly quotes, and on frequent rule churn.

  It's done when seeded scenarios trigger each alert exactly once.
- **ARCHITECTURE §8.7:** the listed rent must be the price charged when no rule applies. Alert ops when it is more than 25% below the locality median for the same occupancy, or when clamps trigger on more than 20% of quotes in a week.
- **PRODUCT_CONTEXT:** ops get alerted when a listed rent is far below the locality median, or when the premium cap or rent band keeps clamping prices.
- **What exists:**
  - the market lookup and median of the pricing editor (ADR 0041);
  - quotes that keep the limits that held them back (ADR 0039);
  - rule sets with their activations (ADR 0038).

## Decision

1. **One table, `pricing_alerts`.** Each alert has:
   - its kind and its PG, and the room for a rent alert;
   - the numbers that raised it, as they were, with the PG's and room's names for showing it;
   - when it was raised, and when, by whom and how it was resolved.

   A unique **key** makes each alert once-only. A check inserts and skips one whose key exists, however often it runs:
   - **a rent below the market** is keyed by the room and its listed rent. A new rent that's still too low is a new alert;
   - **clamps** and **churn** are keyed by the PG and the week, Monday to Sunday in India.
2. **The checks:**
   - **A rent below the market**, nightly at 01:00 in India. Every active room of every published PG is compared with its market: the median listed rent for the same sharing in its locality's other published PGs, the median the editor shows. It's an alert below 75% of the median, once there are **at least three** to compare with; fewer say too little. The same check resolves an open rent alert once its room no longer qualifies, "by the nightly check", with no person named.
   - **Limits often held prices back**, in the same nightly job, for last week: a PG whose quotes a limit held back in more than 20% of them, once it had **at least ten** quotes. Fewer say too little.
   - **Rules keep changing**, as each rule set goes into force, in the same transaction: more than **three** activations of a PG's rules in a week. Prices that keep moving confuse students and can hide trouble.

   These thresholds are named constants in `pricing/domain/alerts.py`. The 25% and 20% come from ARCHITECTURE §8.7. The minimum counts and the weekly churn limit are ours, and are easy to change.
3. **Ops read and resolve them:**
   - `GET /v1/ops/pricing-alerts?status=open|resolved` lists them, newest first, a page at a time;
   - `POST /v1/ops/pricing-alerts/{id}/resolve` resolves one with an optional note of what they found. It's audited. A resolved alert answers `409 INVALID_TRANSITION`.

   Both are for ops and admins, as the rule sets are. The ops console's **Pricing alerts** page shows each alert in a sentence from its numbers, links to its PG's pricing editor, and resolves it in the page.
4. **An alert doesn't come back once resolved.** Its key stays taken. Ops who looked and found a low rent intended aren't told again each night. A changed rent, or another week, is a new key.

## Consequences

- **"Done when."** API tests seed each scenario and run its check twice:
  - a ₹7,000 room beside ₹10,000, ₹10,000 and ₹12,000 is raised once. At ₹8,000 it resolves itself, and at ₹6,500 it's a new alert;
  - 3 of 10 quotes in a week held back by the owner's limit raise one alert for that week;
  - the fourth activation in a week raises one, and the fifth doesn't.

  A browser test resolves a churn alert from the page.
- **Cost:** the nightly market check reads every active room once and groups them in memory. The clamp check counts a week of quotes per PG. Both are fine for a city, and the quote count can use an index on `quoted_on` when quotes grow.
- **Owners** don't see these alerts. Phase 7 can show owners their own rent against the market with the same lookup.
- **Monitoring alerts** stay a separate matter (ARCHITECTURE §19, Phase 8). These are for ops' judgement, not paging anyone.
