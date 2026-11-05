import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Paying a booking's token, from the browser (step 6.1, ADR 0056). The browser never says how
 * much: the API makes the order for exactly the booking's token.
 */

export type PaymentStart = Schemas["PaymentStart"];
export type CheckoutCallback = Schemas["CheckoutCallback"];
export type CheckoutResult = Schemas["CheckoutResult"];

/** The order to open checkout with. Asking again gets the same one. */
export function startTokenPayment(code: string): Promise<PaymentStart> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/bookings/{code}/payment", {
        params: { path: { code } },
        headers,
      }),
    ),
  );
}

/** What checkout handed over, for the API to check and ask the gateway about. Safe to repeat. */
export function finishCheckout(id: string, callback: CheckoutCallback): Promise<CheckoutResult> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/payments/{payment_id}/checkout-callback", {
        params: { path: { payment_id: id } },
        body: callback,
        headers,
      }),
    ),
  );
}

/** The fake gateway's bank says yes: what its checkout would hand over. No money moves. */
export function payAtTestBank(id: string): Promise<CheckoutCallback> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/payments/{payment_id}/test-checkout", {
        params: { path: { payment_id: id } },
        headers,
      }),
    ),
  );
}
