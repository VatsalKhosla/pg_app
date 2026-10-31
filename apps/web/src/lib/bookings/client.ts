import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Bookings' calls from the browser (steps 5.5 to 5.9, ADRs 0049 to 0053): a student reserving a
 * bed, cancelling their own, saying they've moved in, or reporting a room that isn't as shown.
 * Pages read on the server.
 */

export type StudentBooking = Schemas["StudentBooking"];
export type BookingStatus = StudentBooking["status"];
export type DisputeRequest = Schemas["DisputeRequest"];
export type DisputeReason = DisputeRequest["reason"];

/** `refundPaise` is what the student was shown; the API refuses if cancelling now means more or less. */
export function cancelMyBooking(code: string, refundPaise: number): Promise<StudentBooking> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/bookings/{code}/cancel", {
        params: { path: { code } },
        body: { refundPaise },
        headers,
      }),
    ),
  );
}

/** The student has moved in: their time to tell us if the room isn't as shown starts now. */
export function checkInToMyBooking(code: string): Promise<StudentBooking> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/bookings/{code}/check-in", { params: { path: { code } }, headers }),
    ),
  );
}

/** The student's report, with their own ready dispute photos, in their order. */
export function openDispute(code: string, report: DisputeRequest): Promise<StudentBooking> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/bookings/{code}/disputes", {
        params: { path: { code } },
        body: report,
        headers,
      }),
    ),
  );
}

/**
 * A bed of the quote's room held for the stay. With ``visit``, on the spot at the student's
 * visit (step 5.9). ``idempotencyKey`` is the same on every retry of one reservation, so a retry
 * gets the first answer back instead of a second hold.
 */
export function holdBed(
  quote: string,
  visit: string | null,
  idempotencyKey: string,
): Promise<StudentBooking> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/bookings", {
        params: { header: { "Idempotency-Key": idempotencyKey } },
        body: visit === null ? { quote } : { quote, visit },
        headers,
      }),
    ),
  );
}
