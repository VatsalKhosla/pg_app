import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Bookings' calls from the browser (steps 5.5 and 5.6, ADRs 0049 and 0050): a student cancelling
 * their own, or saying they've moved in. Pages read on the server.
 */

export type StudentBooking = Schemas["StudentBooking"];
export type BookingStatus = StudentBooking["status"];

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
