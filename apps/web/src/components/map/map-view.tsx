"use client";

import dynamic from "next/dynamic";

import { publicEnv } from "@/config/env";

import type { MapViewProps, ShortPrice } from "./map-provider";

// The map's code and styles load only where the map shows: the desktop's split view, or the
// phone's map view once opened, never with the list alone (BUILD_PLAN 3.5).
const MapLibreMapView = dynamic(() => import("./maplibre/map-view"), {
  ssr: false,
  loading: () => (
    <div className="h-full min-h-72 w-full animate-pulse bg-muted motion-reduce:animate-none" />
  ),
});

/** The search map, from whichever map this site is set up with (ADR 0031); none without tiles. */
export function MapView(props: MapViewProps & { shortPrice: ShortPrice }) {
  const tiles = publicEnv.mapTiles;
  if (tiles === undefined) return null;
  return <MapLibreMapView {...props} tiles={tiles} />;
}

export const hasSearchMap = publicEnv.mapTiles !== undefined;
