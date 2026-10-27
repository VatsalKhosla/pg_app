import "server-only";

import type { Schemas } from "@pg-platform/api-client";
import { unstable_cache } from "next/cache";

import { serverEnv } from "@/config/server-env";

import { createWebApiClient, unwrap } from "./client";
import { ApiError } from "./errors";
import { SERVER_TIMEOUT_MS } from "./server";

export type PublicListing = Schemas["PublicListing"];

/**
 * What anyone may read from the API, the same for every visitor: fetched without their cookies
 * and kept in Next's data cache across requests (ADR 0030). Pages still render per request, for
 * their CSP nonce; the cache makes that cheap. A listing is fresh within a minute, as the API's
 * own Cache-Control says; step 3.6 adds revalidation on demand, by tag.
 */
const LISTING_REVALIDATE_SECONDS = 60;

function publicApi() {
  return createWebApiClient({ baseUrl: serverEnv.apiUrl, timeoutMs: SERVER_TIMEOUT_MS });
}

/** The tag a listing's cached data carries, for revalidating it on demand. */
export function listingTag(slug: string): string {
  return `listing:${slug}`;
}

/** A live listing by its slug, or null if the public can't see it (cached as such too). */
export async function getPublicListing(slug: string): Promise<PublicListing | null> {
  const cached = unstable_cache(
    async () => {
      try {
        return await unwrap(
          publicApi().GET("/v1/properties/{slug}", { params: { path: { slug } } }),
        );
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    ["public-listing", slug],
    { revalidate: LISTING_REVALIDATE_SECONDS, tags: ["listings", listingTag(slug)] },
  );
  return cached();
}
