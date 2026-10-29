import type { MetadataRoute } from "next";

import { publicEnv } from "@/config/env";
import { getSearchPlaces, getSitemapListings } from "@/lib/api/public";
import { isIndexable, type TrustPage, trustPages } from "@/lib/trust/pages";

// Made when asked, from data the server caches (tags "listings"), never at build time, when there
// is no API to ask.
export const dynamic = "force-dynamic";

/**
 * Every page search engines should find (step 3.6, ADR 0032): the home page and search, a
 * landing page for each campus and locality with PGs, every PG the public may see, with when it
 * last changed, and the trust pages that are final (step 3.8). Private areas aren't listed;
 * robots.txt names this file.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [places, listings] = await Promise.all([getSearchPlaces(), getSitemapListings()]);
  const url = (path: string) => new URL(path, publicEnv.siteUrl).toString();
  return [
    { url: url("/") },
    { url: url("/search") },
    ...(Object.keys(trustPages) as TrustPage[])
      .filter((page) => isIndexable(page))
      .map((page) => ({ url: url(trustPages[page]) })),
    ...places.items.map((place) => ({
      url: url(place.kind === "campus" ? `/pg-near/${place.slug}` : `/pg-in/${place.slug}`),
    })),
    ...listings.map((listing) => ({
      url: url(`/pg/${listing.slug}`),
      lastModified: listing.changedAt,
    })),
  ];
}
