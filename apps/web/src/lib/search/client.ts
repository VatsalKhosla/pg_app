import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";

import type { PinsQuery, SearchQuery } from "./params";

/**
 * Search's calls from the browser (ADR 0031). TanStack Query passes each an AbortSignal, so a
 * request the person has moved on from is cancelled rather than left to land late.
 */

export type SearchPage = Schemas["SearchPage"];
export type SearchCard = Schemas["SearchCard"];
export type MapPins = Schemas["MapPins"];
export type MapPin = Schemas["MapPin"];
export type PublicListing = Schemas["PublicListing"];

export function searchListings(query: SearchQuery, signal?: AbortSignal): Promise<SearchPage> {
  return unwrap(browserApi.GET("/v1/search/properties", { params: { query }, signal }));
}

export function mapPins(query: PinsQuery, signal?: AbortSignal): Promise<MapPins> {
  return unwrap(browserApi.GET("/v1/map/pins", { params: { query }, signal }));
}

export function publicListing(slug: string, signal?: AbortSignal): Promise<PublicListing> {
  return unwrap(browserApi.GET("/v1/properties/{slug}", { params: { path: { slug } }, signal }));
}
