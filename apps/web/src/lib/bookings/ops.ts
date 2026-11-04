import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * What ops do with a booking, from the browser (step 5.10, ADR 0054). Each goes through the state
 * machine, and each that changes the booking says why. Pages read on the server.
 */

export type OpsBooking = Schemas["OpsBooking"];
export type OpsAction = OpsBooking["actions"][number];
export type MoveInReminder = Schemas["MoveInReminder"];

export function confirmForOwner(code: string, reason: string) {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/bookings/{code}/confirm", {
        params: { path: { code } },
        body: { reason },
        headers,
      }),
    ),
  );
}

export function rejectForOwner(code: string, reason: string) {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/bookings/{code}/reject", {
        params: { path: { code } },
        body: { reason },
        headers,
      }),
    ),
  );
}

export function cancelForOwner(code: string, reason: string) {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/bookings/{code}/owner-cancel", {
        params: { path: { code } },
        body: { reason },
        headers,
      }),
    ),
  );
}

export function recordMoveOut(code: string, movedOutOn: string, reason: string) {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/bookings/{code}/move-out", {
        params: { path: { code } },
        body: { movedOutOn, reason },
        headers,
      }),
    ),
  );
}

/** Texts the student to say they've moved in: `sent` is false when they were asked today. */
export function remindMoveIn(code: string): Promise<MoveInReminder> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/bookings/{code}/move-in-reminder", {
        params: { path: { code } },
        headers,
      }),
    ),
  );
}
