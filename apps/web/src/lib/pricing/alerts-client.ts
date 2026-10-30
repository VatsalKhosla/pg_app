import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/** Pricing's integrity alerts from the browser (step 4.8, ADR 0043): ops resolve one. */

export type PricingAlert = Schemas["PricingAlertInfo"];

export function resolveAlert(alertId: string, note: string): Promise<PricingAlert> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/pricing-alerts/{alert_id}/resolve", {
        params: { path: { alert_id: alertId } },
        body: { note },
        headers,
      }),
    ),
  );
}
