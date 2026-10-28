import type { operations } from "@pg-platform/api-client";
import {
  createLoader,
  createSerializer,
  type inferParserType,
  parseAsArrayOf,
  parseAsBoolean,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
} from "nuqs/server";

/**
 * Search's state lives in the URL (ARCHITECTURE §16, ADR 0031), so a shared link reproduces the
 * same results. These parsers are the one definition: the server page loads them, the client
 * reads and writes them through nuqs, and their keys are the API's own parameter names. Imported
 * from "nuqs/server" so the server can use them too.
 */

export const SORTS = ["recommended", "price_asc", "price_desc", "distance", "newest"] as const;
export const GENDERS = ["girls", "boys", "coed"] as const;
export const OCCUPANCIES = ["single", "double", "triple", "quad"] as const;
export const MEALS = ["none", "breakfast", "two", "three", "four"] as const;
export const VIEWS = ["list", "map"] as const;
export const RADII_M = [1_000, 2_000, 3_000, 5_000] as const;

export const searchParsers = {
  campus: parseAsString,
  radius_m: parseAsInteger,
  locality: parseAsString,
  bbox: parseAsString,
  move_in_month: parseAsString,
  budget_min_paise: parseAsInteger,
  budget_max_paise: parseAsInteger,
  gender: parseAsStringLiteral(GENDERS),
  occupancy: parseAsStringLiteral(OCCUPANCIES),
  meals: parseAsStringLiteral(MEALS),
  ac: parseAsBoolean,
  attached_bath: parseAsBoolean,
  amenities: parseAsArrayOf(parseAsString),
  available: parseAsBoolean,
  q: parseAsString,
  sort: parseAsStringLiteral(SORTS),
  // The phone's view: the list first, or the map (the desktop shows both).
  view: parseAsStringLiteral(VIEWS),
};

export const loadSearchParams = createLoader(searchParsers);
export const serializeSearch = createSerializer(searchParsers);

export type SearchState = inferParserType<typeof searchParsers>;
export type SearchQuery = NonNullable<operations["searchSearchProperties"]["parameters"]["query"]>;
export type PinsQuery = NonNullable<operations["searchMapPins"]["parameters"]["query"]>;

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/u;
const MONTH = /^[0-9]{4}-(0[1-9]|1[0-2])$/u;
const NUMBER = String.raw`-?[0-9]{1,3}(\.[0-9]{1,15})?`;
const BBOX = new RegExp(`^${NUMBER},${NUMBER},${NUMBER},${NUMBER}$`, "u");

function slug(value: string | null): string | undefined {
  return value !== null && SLUG.test(value) && value.length <= 64 ? value : undefined;
}

function money(value: number | null): number | undefined {
  return value !== null && Number.isSafeInteger(value) && value >= 0 ? value : undefined;
}

/**
 * What the filters ask the API for: the same for search and the map's pins. Anything a hand-edited
 * URL got wrong is left out rather than sent, so the page still shows something.
 */
function filters(state: SearchState) {
  const text = state.q?.trim().slice(0, 100);
  return {
    move_in_month:
      state.move_in_month !== null && MONTH.test(state.move_in_month)
        ? state.move_in_month
        : undefined,
    budget_min_paise: money(state.budget_min_paise),
    budget_max_paise: money(state.budget_max_paise),
    gender: state.gender ?? undefined,
    occupancy: state.occupancy ?? undefined,
    meals: state.meals ?? undefined,
    ac: state.ac ?? undefined,
    attached_bath: state.attached_bath ?? undefined,
    amenities: (state.amenities ?? []).filter((amenity) => SLUG.test(amenity)).slice(0, 20),
    available: state.available ?? undefined,
    q: text === undefined || text === "" ? undefined : text,
  };
}

// A phone shows four or five at once: a dozen fills the first screens, and "Show more" the rest.
const PAGE_SIZE = 12;

/** One place to search around: a map area wins, then a campus, then a locality. */
export function searchQuery(state: SearchState, cursor?: string): SearchQuery {
  const bbox = state.bbox !== null && BBOX.test(state.bbox) ? state.bbox : undefined;
  const campus = bbox === undefined ? slug(state.campus) : undefined;
  const locality = bbox === undefined && campus === undefined ? slug(state.locality) : undefined;
  const radius = (RADII_M as readonly number[]).includes(state.radius_m ?? 0)
    ? (state.radius_m ?? undefined)
    : undefined;
  // Distance needs a campus to measure from; without one, recommended does instead.
  const sort = state.sort === "distance" && campus === undefined ? undefined : state.sort;
  return {
    ...filters(state),
    bbox,
    campus,
    radius_m: campus === undefined ? undefined : radius,
    locality,
    sort: sort ?? undefined,
    cursor,
    limit: PAGE_SIZE,
  };
}

/** The pins for the map's area, with the same filters as the list. */
export function pinsQuery(state: SearchState, area: string, zoom: number): PinsQuery {
  return { ...filters(state), bbox: area, zoom: Math.min(20, Math.max(5, Math.round(zoom))) };
}
