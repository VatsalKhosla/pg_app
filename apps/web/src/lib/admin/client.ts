import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * The admin console's calls from the browser (step 4.1, ADR 0036): each policy's next version,
 * and rent bands. Pages read on the server.
 */

export type FeePolicyInput = Schemas["FeePolicyInput"];
export type BookingPolicyInput = Schemas["BookingPolicyInput"];
export type PricingCapsInput = Schemas["PricingCapsInput"];
export type RentBandInput = Schemas["RentBandInput"];

export function changeFeePolicy(body: FeePolicyInput) {
  return withCsrf((headers) =>
    unwrap(browserApi.POST("/v1/admin/policies/fee", { body, headers })),
  );
}

export function changeBookingPolicy(body: BookingPolicyInput) {
  return withCsrf((headers) =>
    unwrap(browserApi.POST("/v1/admin/policies/booking", { body, headers })),
  );
}

export function changePricingCaps(body: PricingCapsInput) {
  return withCsrf((headers) =>
    unwrap(browserApi.POST("/v1/admin/policies/caps", { body, headers })),
  );
}

export function setRentBand(body: RentBandInput) {
  return withCsrf((headers) => unwrap(browserApi.POST("/v1/admin/rent-bands", { body, headers })));
}

export function endRentBand(id: string) {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/admin/rent-bands/{band_id}/end", {
        params: { path: { band_id: id } },
        body: { note: "" },
        headers,
      }),
    ),
  );
}
