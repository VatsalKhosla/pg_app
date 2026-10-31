import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Ops settling a student's report that their room isn't as shown (step 5.7, ADR 0051), from the
 * browser. Pages read on the server.
 */

export type OpsDispute = Schemas["OpsDispute"];
export type Outcome = Schemas["ResolveRequest"]["outcome"];

/** Refund (the bed released, the token refunded in full) or uphold (the stay goes ahead). */
export function resolveDispute(id: string, outcome: Outcome, notes: string): Promise<OpsDispute> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/disputes/{dispute_id}/resolve", {
        params: { path: { dispute_id: id } },
        body: { outcome, notes },
        headers,
      }),
    ),
  );
}
