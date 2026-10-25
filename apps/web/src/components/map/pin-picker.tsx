"use client";

import dynamic from "next/dynamic";

import { publicEnv } from "@/config/env";

import type { PinPickerProps } from "./map-provider";

// The map's code and styles load only where a pin picker shows, never with the page itself.
const MapLibrePinPicker = dynamic(() => import("./maplibre/pin-picker"), {
  ssr: false,
  loading: () => (
    <div className="h-72 w-full animate-pulse rounded-md bg-muted motion-reduce:animate-none sm:h-96" />
  ),
});

/**
 * The pin picker, from whichever map this site is set up with (ADR 0023). Without map tiles it
 * shows nothing: the form around it takes the pin by GPS or typed coordinates.
 */
export function PinPicker(props: PinPickerProps) {
  const tiles = publicEnv.mapTiles;
  if (tiles === undefined) return null;
  return <MapLibrePinPicker {...props} tiles={tiles} />;
}

/** Whether there's a map at all, so the form can say how to place the pin without one. */
export const hasMap = publicEnv.mapTiles !== undefined;
