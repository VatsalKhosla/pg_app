"use client";

import dynamic from "next/dynamic";

import { publicEnv } from "@/config/env";

import { hasAnyMap, useMapChoice } from "./choice";
import type { MapViewProps, ShortPrice } from "./map-provider";

const placeholder = () => (
  <div className="h-full min-h-72 w-full animate-pulse bg-muted motion-reduce:animate-none" />
);

// The map's code and styles load only where the map shows: the desktop's split view, or the
// phone's map view once opened, never with the list alone (BUILD_PLAN 3.5). Only the adapter this
// site uses is ever fetched (ADR 0069).
const MapLibreMapView = dynamic(() => import("./maplibre/map-view"), {
  ssr: false,
  loading: placeholder,
});
const GoogleMapView = dynamic(() => import("./google/map-view"), {
  ssr: false,
  loading: placeholder,
});

/**
 * The search map, from whichever map this site is set up with (ADR 0031, 0069): Google's, else
 * MapLibre's tiles, else none.
 */
export function MapView(props: MapViewProps & { shortPrice: ShortPrice }) {
  const choice = useMapChoice();
  const { googleMaps, mapTiles } = publicEnv;
  if (choice === "google" && googleMaps !== undefined) {
    return <GoogleMapView {...props} config={googleMaps} />;
  }
  if (choice === "maplibre" && mapTiles !== undefined) {
    return <MapLibreMapView {...props} tiles={mapTiles} />;
  }
  if (choice === "failed") {
    return (
      <p className="m-4 rounded-md border border-dashed bg-background p-4 text-sm text-muted-foreground">
        {props.text.failed}
      </p>
    );
  }
  return null;
}

export const hasSearchMap = hasAnyMap;
