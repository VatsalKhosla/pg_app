import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Bookings' calls from the browser (step 5.5, ADR 0049): a student cancelling their own. Pages
 * read on the server.
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
