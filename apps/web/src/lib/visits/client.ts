import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Visits' calls from the browser (step 3.7, ADR 0033): a student's request and cancellation, ops
 * booking and cancelling, and an agent's check-in and outcome. Pages read on the server.
 */

export type StudentVisit = Schemas["StudentVisit"];
export type StaffVisit = Schemas["StaffVisit"];
export type Outcome = Schemas["VisitOutcomeRequest"]["outcome"];

/** `analyticsId` is the tab's anonymous id, if it reports analytics (ADR 0035). */
export function requestVisit(
  property: string,
  starts: string[],
  analyticsId?: string,
): Promise<StudentVisit> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/visits", {
        body: { property, starts, ...(analyticsId === undefined ? {} : { analyticsId }) },
        headers,
      }),
    ),
  );
}

export function cancelMyVisit(id: string): Promise<StudentVisit> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/visits/{visit_id}/cancel", {
        params: { path: { visit_id: id } },
        headers,
      }),
    ),
  );
}

export function scheduleVisit(id: string, at: string, agent: string): Promise<StaffVisit> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/visits/{visit_id}/schedule", {
        params: { path: { visit_id: id } },
        body: { at, agent },
        headers,
      }),
    ),
  );
}

export function cancelVisit(id: string, reason: string): Promise<StaffVisit> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/visits/{visit_id}/cancel", {
        params: { path: { visit_id: id } },
        body: { reason },
        headers,
      }),
    ),
  );
}

export function checkIn(
  id: string,
  position: { lat: number; lng: number },
  accuracyM: number,
): Promise<StaffVisit> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/field/visits/{visit_id}/check-in", {
        params: { path: { visit_id: id } },
        body: { position, accuracyM: Math.round(accuracyM) },
        headers,
      }),
    ),
  );
}

export function recordOutcome(id: string, outcome: Outcome, note: string): Promise<StaffVisit> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/field/visits/{visit_id}/outcome", {
        params: { path: { visit_id: id } },
        body: { outcome, note },
        headers,
      }),
    ),
  );
}
