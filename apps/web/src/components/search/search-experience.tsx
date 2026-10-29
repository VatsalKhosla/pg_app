"use client";

import { keepPreviousData, skipToken, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { List, Map as MapIcon, SlidersHorizontal } from "lucide-react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useQueryStates } from "nuqs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type Bounds,
  type MapPin,
  type MapViewText,
  NCR_BOUNDS,
} from "@/components/map/map-provider";
import { hasSearchMap, MapView } from "@/components/map/map-view";
import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/money";
import { around, bboxParam, enclosing, parseBbox } from "@/lib/search/area";
import { mapPins, searchListings, type SearchPage } from "@/lib/search/client";
import { priceLabel, shortRupees } from "@/lib/search/labels";
import { track } from "@/lib/analytics";
import { searchProperties } from "@/lib/search/analytics";
import { pinsQuery, searchParsers, searchQuery } from "@/lib/search/params";
import { cn } from "@/lib/utils";

import type { SheetSnap } from "./bottom-sheet";
import {
  type Amenity,
  CLEARED,
  DEFAULT_RADIUS_M,
  type Locality,
  type MonthOption,
  type Place,
  SearchBar,
  type SearchPatch,
} from "./filters";
import { useDebounced, useMediaQuery } from "./hooks";
import { Results } from "./results";

// Code most visits never run loads when it's first needed (frontend rules): the filters' sheet
// when it's opened, and the map's own pieces with the map.
const FiltersSheet = dynamic(() => import("./filters-sheet").then((module) => module.FiltersSheet));
const BottomSheet = dynamic(() => import("./bottom-sheet").then((module) => module.BottomSheet));
const PinPreview = dynamic(() => import("./pin-preview").then((module) => module.PinPreview));

// The desktop's split view starts here (Tailwind's lg); below it, the list comes first.
const DESKTOP = "(min-width: 1024px)";
// How long the map rests before its area counts (ARCHITECTURE §10.3).
const SETTLE_MS = 300;
// A locality has no outline yet, so the map shows this far around its centre.
const LOCALITY_VIEW_M = 1_500;
// Room around the campuses when nothing narrower is asked for.
const EVERYWHERE_MARGIN_M = 2_000;

interface Area {
  bounds: Bounds;
  bbox: string;
  zoom: number;
  /** The place the map was showing then, if any: a new one takes the map there instead. */
  targetKey: string | null;
}

/**
 * Search (step 3.5, ADR 0031): the URL holds what's asked (nuqs), TanStack Query fetches the
 * answers and drops those the person has moved on from, and the map, when it shows, follows the
 * same filters. The desktop shows the list beside the map; a phone shows the list first and the
 * map on request, with the list in a sheet over it. The map's code loads only when it shows.
 */
export function SearchExperience({
  initial,
  initialProblem,
  campuses,
  localities,
  stations,
  amenities,
  months,
}: {
  initial: SearchPage | null;
  initialProblem: string | null;
  campuses: readonly Place[];
  localities: readonly Locality[];
  stations: readonly Place[];
  amenities: readonly Amenity[];
  months: readonly MonthOption[];
}) {
  const t = useTranslations("Search");
  const tPg = useTranslations("Pg");
  const [state, setState] = useQueryStates(searchParsers);
  const query = useMemo(() => searchQuery(state), [state]);
  const update = useCallback(
    (patch: SearchPatch) => {
      void setState(patch);
    },
    [setState],
  );
  const clearAll = useCallback(() => {
    update(CLEARED);
  }, [update]);

  // The server rendered the first page for the URL as it arrived: that answer stands until the
  // search changes. A search it couldn't answer isn't asked again.
  const [serverQuery] = useState(() => JSON.stringify(query));
  const fromServer = JSON.stringify(query) === serverQuery;
  const results = useInfiniteQuery({
    queryKey: ["search", query],
    queryFn: ({ pageParam, signal }) => searchListings({ ...query, cursor: pageParam }, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    // A function, so the types know there may be none.
    initialData: () =>
      fromServer && initial !== null ? { pages: [initial], pageParams: [undefined] } : undefined,
    placeholderData: keepPreviousData,
    enabled: !(fromServer && initialProblem !== null),
  });
  const cards = useMemo(
    () => results.data?.pages.flatMap((page) => page.items) ?? [],
    [results.data],
  );

  // The funnel's first step (step 3.9): once for each search whose first page has come.
  const firstPage = results.data?.pages[0];
  const reported = useRef<string | null>(null);
  useEffect(() => {
    if (firstPage === undefined || results.isPlaceholderData) return;
    const key = JSON.stringify(query);
    if (reported.current === key) return;
    reported.current = key;
    track("search_performed", searchProperties(query, firstPage.items.length));
  }, [firstPage, query, results.isPlaceholderData]);

  // Where the map goes: the campus or locality chosen. A map area is where the map already is.
  const campus = campuses.find((place) => place.slug === query.campus);
  const locality = localities.find((place) => place.slug === query.locality);
  const radius = query.radius_m ?? DEFAULT_RADIUS_M;
  const target = useMemo(() => {
    if (campus !== undefined) {
      return {
        key: `campus:${campus.slug}:${String(radius)}`,
        bounds: around(campus.location, radius),
      };
    }
    if (locality !== undefined) {
      return { key: `locality:${locality.slug}`, bounds: around(locality.center, LOCALITY_VIEW_M) };
    }
    return null;
  }, [campus, locality, radius]);
  const everywhere = useMemo(
    () =>
      enclosing(
        campuses.map((place) => place.location),
        EVERYWHERE_MARGIN_M,
      ) ?? NCR_BOUNDS,
    [campuses],
  );

  const isDesktop = useMediaQuery(DESKTOP);
  const onPhoneMap = !isDesktop && state.view === "map";
  const mapShown = hasSearchMap && (isDesktop || state.view === "map");

  // The map's area once it has rested, which the pins are for; with search as I move the map,
  // the person's own moves become the search's area too.
  const [area, setArea] = useState<Area | null>(null);
  const [searchAsMove, setSearchAsMove] = useState(true);
  const [movedAway, setMovedAway] = useState(false);
  const movedByPerson = useRef(false);
  const settle = useDebounced((bounds: Bounds, zoom: number) => {
    const bbox = bboxParam(bounds);
    setArea({ bounds, bbox, zoom, targetKey: target?.key ?? null });
    const byPerson = movedByPerson.current;
    movedByPerson.current = false;
    if (!byPerson) return;
    if (searchAsMove) {
      update({ bbox, campus: null, locality: null, radius_m: null });
    } else {
      setMovedAway(true);
    }
  }, SETTLE_MS);
  const onBoundsChange = useCallback(
    (bounds: Bounds, zoom: number, byPerson: boolean) => {
      // Any move of the person's in a burst counts, even if the page's own came last.
      if (byPerson) movedByPerson.current = true;
      settle(bounds, zoom);
    },
    [settle],
  );
  const searchHere = () => {
    if (area === null) return;
    update({ bbox: area.bbox, campus: null, locality: null, radius_m: null });
    setMovedAway(false);
  };

  const pinsParams = mapShown && area !== null ? pinsQuery(state, area.bbox, area.zoom) : null;
  const pins = useQuery({
    queryKey: ["map-pins", pinsParams],
    queryFn: pinsParams === null ? skipToken : ({ signal }) => mapPins(pinsParams, signal),
    placeholderData: keepPreviousData,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [snap, setSnap] = useState<SheetSnap>("peek");
  const [filtersOpen, setFiltersOpen] = useState(false);
  // Once opened, the sheet stays mounted, so it can animate closed and open again at once.
  const [filtersUsed, setFiltersUsed] = useState(false);
  const openFilters = useCallback(() => {
    setFiltersUsed(true);
    setFiltersOpen(true);
  }, []);
  const mapRegion = useRef<HTMLDivElement>(null);
  const selectedPin =
    selectedId === null ? undefined : pins.data?.pins.find((pin) => pin.id === selectedId);
  // A pin the filters have since taken off the map is no longer selected.
  if (selectedId !== null && pins.data !== undefined && selectedPin === undefined) {
    setSelectedId(null);
  }

  const onPinSelect = useCallback((id: string) => {
    setSelectedId(id);
    setSnap("peek");
  }, []);
  const closePreview = () => {
    const id = selectedId;
    setSelectedId(null);
    if (id === null) return;
    // Back to the pin it came from.
    mapRegion.current?.querySelector<HTMLElement>(`[data-pin-id="${CSS.escape(id)}"]`)?.focus();
  };

  const price = useCallback(
    (min: number, max: number) =>
      min === max
        ? t("card.onePrice", { price: formatINR(min) })
        : t("card.price", { min: formatINR(min), max: formatINR(max) }),
    [t],
  );
  const markers = useMemo<MapPin[]>(
    () =>
      (pins.data?.pins ?? []).map((pin) => ({
        id: pin.id,
        position: { lat: pin.lat, lng: pin.lng },
        label: priceLabel(pin.minRentPaise, pin.maxRentPaise),
        description: t("map.pin", {
          price: price(pin.minRentPaise, pin.maxRentPaise),
          gender: tPg(`gender.${pin.genderPolicy}`),
          verified: String(pin.verified),
        }),
        verified: pin.verified,
        minRentPaise: pin.minRentPaise,
      })),
    [pins.data, price, t, tPg],
  );
  const mapText = useMemo<MapViewText>(
    () => ({
      map: t("map.label"),
      zoomIn: t("map.zoomIn"),
      zoomOut: t("map.zoomOut"),
      credits: t("map.credits"),
      twoFingers: t("map.twoFingers"),
      ctrlScroll: t("map.ctrlScroll"),
      cmdScroll: t("map.cmdScroll"),
      failed: t("map.failed"),
      // Filled in by the map, which knows each cluster's count and lowest price.
      cluster: t.raw("map.cluster") as string,
      campus: t.raw("map.campus") as string,
    }),
    [t],
  );

  // Where it starts: where it last was (a phone's map opened again) unless a place has been
  // chosen since, else what's asked.
  const lastView = area !== null && area.targetKey === (target?.key ?? null) ? area.bounds : null;
  const initialView = lastView ?? parseBbox(query.bbox) ?? target?.bounds ?? everywhere;

  const showMap = () => {
    void setState({ view: "map" }, { history: "push" });
  };
  const showList = () => {
    setSelectedId(null);
    void setState({ view: null }, { history: "push" });
  };
  const activeId = hoveredId ?? selectedId;
  const list = (
    <Results
      results={results}
      problem={fromServer ? initialProblem : null}
      hoveredId={activeId}
      onHover={setHoveredId}
      onClear={clearAll}
    />
  );

  return (
    <div
      className={cn(
        hasSearchMap &&
          "lg:grid lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,34rem)_minmax(0,1fr)]",
      )}
    >
      <div
        className={cn(
          "space-y-4 px-4 pt-4 pb-24 sm:px-6 lg:pb-8",
          !hasSearchMap && "mx-auto w-full max-w-3xl",
          state.view === "map" && "max-lg:hidden",
        )}
      >
        <SearchBar state={state} query={query} onChange={update} onOpenFilters={openFilters} />
        {onPhoneMap ? null : list}
      </div>

      {hasSearchMap ? (
        <div
          ref={mapRegion}
          onKeyDown={(event) => {
            if (event.key === "Escape" && selectedId !== null) closePreview();
          }}
          className={cn(
            "lg:sticky lg:top-16 lg:h-[calc(100dvh-4rem)] lg:border-l",
            state.view === "map"
              ? "max-lg:fixed max-lg:inset-x-0 max-lg:top-16 max-lg:bottom-0 max-lg:z-30 max-lg:bg-background"
              : "max-lg:hidden",
          )}
        >
          <div className="relative h-full w-full">
            {mapShown ? (
              <MapView
                pins={markers}
                selectedId={selectedId}
                hoveredId={hoveredId}
                onBoundsChange={onBoundsChange}
                onPinSelect={onPinSelect}
                onPinHover={setHoveredId}
                campuses={campuses}
                chosenCampus={campus?.slug ?? null}
                stations={stations}
                initial={initialView}
                target={target}
                text={mapText}
                shortPrice={shortRupees}
              />
            ) : (
              <div className="h-full w-full bg-muted" />
            )}
            {/* The strip lets the map have its empty space: only its controls take presses. */}
            <div className="pointer-events-none absolute top-3 right-14 left-3 z-10 flex flex-wrap items-start gap-2 *:pointer-events-auto">
              <Button
                variant="outline"
                size="sm"
                className="bg-background shadow-sm lg:hidden"
                onClick={openFilters}
              >
                <SlidersHorizontal aria-hidden="true" />
                {t("filters.open")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="bg-background shadow-sm lg:hidden"
                onClick={showList}
              >
                <List aria-hidden="true" />
                {t("map.hide")}
              </Button>
              <label className="flex h-8 items-center gap-2 rounded-md border bg-background px-3 text-sm shadow-sm">
                <input
                  type="checkbox"
                  checked={searchAsMove}
                  onChange={(event) => {
                    setSearchAsMove(event.target.checked);
                    setMovedAway(false);
                  }}
                  className="size-4 accent-primary"
                />
                {t("filters.searchAsMove")}
              </label>
              {!searchAsMove && movedAway ? (
                <Button size="sm" className="shadow-sm" onClick={searchHere}>
                  {t("map.searchHere")}
                </Button>
              ) : null}
              {pins.data?.truncated === true ? (
                <p
                  role="status"
                  className="max-w-xs basis-full rounded-md border bg-background px-3 py-2 text-sm shadow-sm"
                >
                  {t("map.truncated")}
                </p>
              ) : null}
            </div>
            {selectedPin === undefined ? null : (
              <PinPreview
                pin={selectedPin}
                card={cards.find((card) => card.id === selectedPin.id)}
                onClose={closePreview}
                className="absolute inset-x-3 bottom-31 z-20 lg:right-auto lg:bottom-4 lg:left-4 lg:w-96"
              />
            )}
            {onPhoneMap ? (
              <BottomSheet
                snap={snap}
                onSnapChange={(next) => {
                  setSnap(next);
                  // The list, opened, would cover the preview.
                  if (next !== "peek") setSelectedId(null);
                }}
                label={t("map.sheet")}
                moreLabel={t("map.sheetMore")}
                lessLabel={t("map.sheetLess")}
              >
                {list}
              </BottomSheet>
            ) : null}
          </div>
        </div>
      ) : null}

      {hasSearchMap && state.view !== "map" ? (
        <Button
          className="fixed bottom-6 left-1/2 z-20 -translate-x-1/2 rounded-full px-5 shadow-lg lg:hidden"
          onClick={showMap}
        >
          <MapIcon aria-hidden="true" />
          {t("map.show")}
        </Button>
      ) : null}

      {filtersUsed ? (
        <FiltersSheet
          open={filtersOpen}
          onOpenChange={setFiltersOpen}
          side={isDesktop ? "left" : "bottom"}
          state={state}
          query={query}
          onChange={update}
          campuses={campuses}
          localities={localities}
          amenities={amenities}
          months={months}
        />
      ) : null}
    </div>
  );
}
