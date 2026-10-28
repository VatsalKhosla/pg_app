import "server-only";

import type { operations, Schemas } from "@pg-platform/api-client";
import { unstable_cache } from "next/cache";

import { serverEnv } from "@/config/server-env";

import { createWebApiClient, unwrap } from "./client";
import { ApiError } from "./errors";
import { SERVER_TIMEOUT_MS } from "./server";

export type PublicListing = Schemas["PublicListing"];
type SearchQueryParams = NonNullable<operations["searchSearchProperties"]["parameters"]["query"]>;

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

export type SearchPage = Schemas["SearchPage"];

/** Reference lists for search's filters and map: they change only when the data is reloaded. */
const REFERENCE_REVALIDATE_SECONDS = 3_600;
const SEARCH_REVALIDATE_SECONDS = 30;

export const getSearchReference = unstable_cache(
  async () => {
    const api = publicApi();
    const [campuses, localities, stations, amenities] = await Promise.all([
      unwrap(api.GET("/v1/campuses")),
      unwrap(api.GET("/v1/localities")),
      unwrap(api.GET("/v1/metro-stations")),
      unwrap(api.GET("/v1/amenities")),
    ]);
    return {
      campuses: campuses.items,
      localities: localities.items,
      stations: stations.items,
      amenities: amenities.items,
    };
  },
  ["search-reference"],
  { revalidate: REFERENCE_REVALIDATE_SECONDS, tags: ["reference"] },
);

/**
 * A page of search results for the page's first paint, the same for every visitor asking the
 * same thing: cached for 30 seconds, as the API's Cache-Control says. A search the API can't
 * answer comes back as its problem's detail, for the page to show.
 */
export async function getSearchPage(
  query: SearchQueryParams,
): Promise<{ page: SearchPage } | { problem: string }> {
  const cached = unstable_cache(
    async () => {
      try {
        return {
          page: await unwrap(publicApi().GET("/v1/search/properties", { params: { query } })),
        };
      } catch (error) {
        if (error instanceof ApiError && error.status === 422) {
          return { problem: error.problem?.detail ?? error.message };
        }
        throw error;
      }
    },
    ["search-page", JSON.stringify(query)],
    { revalidate: SEARCH_REVALIDATE_SECONDS, tags: ["listings"] },
  );
  return cached();
}
