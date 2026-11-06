import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/** An owner's own changes, from the browser (Phase 7, ADR 0063). */

export type ManagedBooking = Schemas["ManagedBooking"];
export type DocumentKind = Schemas["DocumentCreate"]["kind"];

/** Confirm a booking at one of the owner's PGs, once its token is in. */
export function confirmBooking(code: string): Promise<ManagedBooking> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/owner/bookings/{code}/confirm", {
        params: { path: { code } },
        headers,
      }),
    ),
  );
}

/** Turn one down, saying why: the student is refunded in full. */
export function rejectBooking(code: string, reason: string): Promise<ManagedBooking> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/owner/bookings/{code}/reject", {
        params: { path: { code } },
        body: { reason },
        headers,
      }),
    ),
  );
}

/** A finished upload, as one of the PG's documents. */
export function addDocument(
  propertyId: string,
  kind: DocumentKind,
  media: string,
): Promise<Schemas["DocumentInfo"]> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/owner/properties/{property_id}/documents", {
        params: { path: { property_id: propertyId } },
        body: { kind, media },
        headers,
      }),
    ),
  );
}
