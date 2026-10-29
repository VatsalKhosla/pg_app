import type { AnalyticsProperties } from "@/lib/analytics";

import type { SearchQuery } from "./params";

const FILTERS = [
  "move_in_month",
  "budget_min_paise",
  "budget_max_paise",
  "gender",
  "occupancy",
  "meals",
  "ac",
  "attached_bath",
  "available",
  "q",
] as const satisfies readonly (keyof SearchQuery)[];

/**
 * What a search reports (step 3.9, ADR 0035): where and how it searched and how much it found.
 * Never the words typed, nor a map area's coordinates: "near me" centres those on the person.
 */
export function searchProperties(query: SearchQuery, results: number): AnalyticsProperties {
  const area =
    query.campus !== undefined
      ? "campus"
      : query.locality !== undefined
        ? "locality"
        : query.bbox !== undefined
          ? "map"
          : "everywhere";
  const filters =
    FILTERS.filter((key) => query[key] !== undefined).length +
    ((query.amenities?.length ?? 0) > 0 ? 1 : 0);
  return {
    area,
    place: query.campus ?? query.locality ?? null,
    filters,
    sort: query.sort ?? "recommended",
    results,
  };
}
