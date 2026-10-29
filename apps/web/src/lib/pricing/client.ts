import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/** Quotes from the browser (step 4.5, ADR 0040): the price is the server's, never worked out here. */

export type Quote = Schemas["QuoteInfo"];

export function createQuote(roomCategory: string, moveIn: string, stayMonths: number) {
  return withCsrf((headers) =>
    unwrap(browserApi.POST("/v1/quotes", { body: { roomCategory, moveIn, stayMonths }, headers })),
  );
}
