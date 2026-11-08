"use client";

import { Search, SlidersHorizontal } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import type { LatLng } from "@/components/map/map-provider";
import { Button } from "@/components/ui/button";
import { controlClasses, Input } from "@/components/ui/input";
import { SORTS, type SearchQuery, type SearchState } from "@/lib/search/params";
import { cn } from "@/lib/utils";

import { useDebounced } from "./hooks";

export interface Place {
  slug: string;
  name: string;
  location: LatLng;
}

export interface Locality {
  slug: string;
  name: string;
  center: LatLng;
}

export interface Amenity {
  slug: string;
  name: string;
}

export interface MonthOption {
  value: string;
  label: string;
}

export type SearchPatch = Partial<SearchState>;

/** The API's radius when none is given (search's `radius_m`). */
export const DEFAULT_RADIUS_M = 3_000;

/** Every filter the sheet sets, cleared; the view stays as it is. */
export const CLEARED: SearchPatch = {
  campus: null,
  radius_m: null,
  locality: null,
  bbox: null,
  move_in_month: null,
  budget_min_paise: null,
  budget_max_paise: null,
  gender: null,
  occupancy: null,
  meals: null,
  ac: null,
  attached_bath: null,
  amenities: null,
  available: null,
  q: null,
  sort: null,
};

/** How many of the sheet's filters are set, for its button. */
export function activeFilters(query: SearchQuery): number {
  return [
    query.campus ?? query.locality,
    query.move_in_month,
    query.budget_min_paise,
    query.budget_max_paise,
    query.gender,
    query.occupancy,
    query.meals,
    query.ac,
    query.attached_bath,
    query.available,
    (query.amenities?.length ?? 0) > 0 ? true : undefined,
  ].filter((value) => value !== undefined && value !== null).length;
}

export const selectClasses = cn(controlClasses, "h-11 pointer-fine:h-10");

/**
 * The text search, the button that opens the filters and the order, above the results. The
 * text goes into the URL a moment after typing stops, or at once on Enter.
 */
export function SearchBar({
  state,
  query,
  onChange,
  onOpenFilters,
}: {
  state: SearchState;
  query: SearchQuery;
  onChange: (patch: SearchPatch) => void;
  onOpenFilters: () => void;
}) {
  const t = useTranslations("Search");
  const textId = useId();
  const sortId = useId();
  // What's typed; it follows the URL when that changes some other way (Clear filters, say).
  const [text, setText] = useState(state.q ?? "");
  const [urlText, setUrlText] = useState(state.q);
  if (state.q !== urlText) {
    setUrlText(state.q);
    setText(state.q ?? "");
  }
  const sendText = useDebounced((value: string) => {
    onChange({ q: value.trim() === "" ? null : value });
  }, 400);
  const count = activeFilters(query);
  const sorts = SORTS.filter((sort) => sort !== "distance" || query.campus !== undefined);

  return (
    <div className="space-y-3 rounded-2xl border border-marigold-border/80 bg-surface-warm p-3.5 shadow-xs">
      <form
        method="get"
        role="search"
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          onChange({ q: text.trim() === "" ? null : text });
        }}
      >
        <label htmlFor={textId} className="sr-only">
          {t("filters.text")}
        </label>
        <div className="relative flex-1">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-primary"
          />
          <Input
            id={textId}
            type="search"
            enterKeyHint="search"
            maxLength={100}
            value={text}
            placeholder={t("filters.textPlaceholder")}
            onChange={(event) => {
              setText(event.target.value);
              sendText(event.target.value);
            }}
            className="rounded-full bg-card ps-10"
          />
        </div>
        <Button
          type="button"
          variant={count > 0 ? "soft" : "outline"}
          shape="pill"
          className="bg-card"
          onClick={onOpenFilters}
        >
          <SlidersHorizontal aria-hidden="true" />
          {t("filters.open")}
          {count > 0 ? (
            <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-semibold text-primary-foreground">
              <span className="sr-only">, </span>
              {t("filters.active", { count })}
            </span>
          ) : null}
        </Button>
      </form>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex items-center gap-2">
          <label htmlFor={sortId} className="text-xs font-semibold text-muted-foreground">
            {t("filters.sort")}
          </label>
          <select
            id={sortId}
            value={query.sort ?? "recommended"}
            onChange={(event) => {
              const sort = event.target.value as (typeof SORTS)[number];
              onChange({ sort: sort === "recommended" ? null : sort });
            }}
            className={cn(
              selectClasses,
              "h-9 w-auto rounded-full bg-card px-3.5 text-xs font-medium pointer-fine:h-8",
            )}
          >
            {sorts.map((sort) => (
              <option key={sort} value={sort}>
                {t(`sort.${sort}`)}
              </option>
            ))}
          </select>
        </div>
        {query.bbox === undefined ? null : (
          <p className="flex items-center gap-2 rounded-full border border-dusk-border bg-dusk-soft px-3.5 py-1 text-xs font-medium text-dusk-soft-foreground">
            {t("filters.mapArea")}
            <button
              type="button"
              onClick={() => {
                onChange({ bbox: null });
              }}
              className="inline-flex min-h-6 items-center rounded px-1 font-semibold text-dusk-soft-foreground underline underline-offset-4 outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-ring"
            >
              {t("filters.clearArea")}
            </button>
          </p>
        )}
      </div>
    </div>
  );
}
