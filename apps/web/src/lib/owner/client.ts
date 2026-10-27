import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/** The owner area's calls from the browser (ADR 0025). Pages read through the server's client. */

export type Acceptance = Schemas["AcceptanceInfo"];

/** Accept the agreement as the owner was shown it: its version and the hash of its text. */
export function acceptAgreement(body: Schemas["AcceptanceCreate"]): Promise<Acceptance> {
  return withCsrf((headers) =>
    unwrap(browserApi.POST("/v1/owner/agreement/acceptances", { body, headers })),
  );
}
