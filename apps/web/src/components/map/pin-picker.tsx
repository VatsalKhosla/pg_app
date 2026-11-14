"use client";

import dynamic from "next/dynamic";

import { publicEnv } from "@/config/env";

import { hasAnyMap, useMapChoice } from "./choice";
import type { PinPickerProps } from "./map-provider";

const placeholder = () => (
  <div className="h-72 w-full animate-pulse rounded-md bg-muted motion-reduce:animate-none sm:h-96" />
);

// The map's code and styles load only where a pin picker shows, never with the page itself; only
// the adapter this site uses is fetched (ADR 0069).
const MapLibrePinPicker = dynamic(() => import("./maplibre/pin-picker"), {
  ssr: false,
  loading: placeholder,
});
const GooglePinPicker = dynamic(() => import("./google/pin-picker"), {
  ssr: false,
  loading: placeholder,
});

/**
 * The pin picker, from whichever map this site is set up with (ADR 0023, 0069). Without a map it
 * shows nothing: the form around it takes the pin by GPS or typed coordinates.
 */
export function PinPicker(props: PinPickerProps) {
  const choice = useMapChoice();
  const { googleMaps, mapTiles } = publicEnv;
  if (choice === "google" && googleMaps !== undefined) {
    return <GooglePinPicker {...props} config={googleMaps} />;
  }
  if (choice === "maplibre" && mapTiles !== undefined) {
    return <MapLibrePinPicker {...props} tiles={mapTiles} />;
  }
  if (choice === "failed") {
    return (
      <p className="rounded-2xl border border-dashed bg-surface p-5 text-sm text-muted-foreground">
        {props.text.failed}
      </p>
    );
  }
  return null;
}

/** Whether there's a map at all, so the form can say how to place the pin without one. */
export const hasMap = hasAnyMap;
