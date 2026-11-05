import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Owners' invoices and reconciliation, from the browser (steps 6.5 and 6.6, ADRs 0061 and 0062).
 * The browser never says how much: an invoice's amounts and its link come from the API.
 */

export type PayLink = Schemas["PayLink"];

/** The fake gateway's bank pays the owner's own invoice. No money moves. */
export function payInvoiceAtTestBank(id: string): Promise<Schemas["WebhookReceipt"]> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/owner/invoices/{invoice_id}/test-payment", {
        params: { path: { invoice_id: id } },
        headers,
      }),
    ),
  );
}

/** Ops ask for a new payment link, after one was cancelled or refused. */
export async function askForPaymentLink(id: string): Promise<void> {
  await withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/invoices/{invoice_id}/payment-link", {
        params: { path: { invoice_id: id } },
        headers,
      }),
    ),
  );
}

/** Ops close what reconciliation found, saying what they did. */
export function resolveIssue(id: string, resolution: string): Promise<Schemas["IssueView"]> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/reconciliation/issues/{issue_id}/resolve", {
        params: { path: { issue_id: id } },
        body: { resolution },
        headers,
      }),
    ),
  );
}
