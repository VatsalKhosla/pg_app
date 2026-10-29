import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Grievances' calls from the browser (step 3.8, ADR 0034): a complaint from anyone, and the
 * grievance officer's team acknowledging and resolving. Pages read on the server.
 */

export type GrievanceInput = Schemas["GrievanceCreate"];
export type GrievanceReceipt = Schemas["GrievanceReceipt"];
export type StaffGrievance = Schemas["StaffGrievance"];
export type GrievanceCategory = Schemas["GrievanceCategory"];

export function complain(body: GrievanceInput): Promise<GrievanceReceipt> {
  return withCsrf((headers) => unwrap(browserApi.POST("/v1/grievances", { body, headers })));
}

export function acknowledgeGrievance(ticket: string, reply: string): Promise<StaffGrievance> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/grievances/{ticket_number}/acknowledge", {
        params: { path: { ticket_number: ticket } },
        body: { reply },
        headers,
      }),
    ),
  );
}

export function resolveGrievance(ticket: string, resolution: string): Promise<StaffGrievance> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/grievances/{ticket_number}/resolve", {
        params: { path: { ticket_number: ticket } },
        body: { resolution },
        headers,
      }),
    ),
  );
}
