import type { LegalDocument } from "../index";

export const refunds: LegalDocument = {
  version: "draft-1",
  updated: "2026-10-29",
  text: String.raw`
## 1. Students pay no fee

{brand} never charges students a booking, convenience or service fee. Searching and visits are free, and cancelling a visit costs nothing.

## 2. The token

When booking opens, you'll reserve a bed with a refundable token of {token}. It counts toward your first month's rent, so it isn't an extra cost.

## 3. Cancelling a reservation

- **Up to {freeCancelDays} days before you move in**: cancel for free, and your token is refunded in full.
- **Later than that**: {lateCancel}
- **If the owner doesn't confirm** your reservation within {confirmHours} hours, it's cancelled and your token is refunded in full.

## 4. When you move in

You have {checkHours} hours after moving in to check the room. If it isn't as shown, tell us within that time: your token is released or refunded the same day, and we'll help you find another verified bed. Only after that time, and without a complaint, does the token count toward your rent.

## 5. How refunds reach you

Refunds go back to the account or card you paid from, through our payment gateway. Your bank may take a few working days to show it.

## 6. Owners

An owner's placement fee, and when it is refunded, follow their agreement with us.

## 7. Questions and complaints

Ask us, or reach our grievance officer, through our [grievances page](/grievances).
`,
};
