import { useSyncExternalStore } from "react";

import { publicEnv } from "@/config/env";

/**
 * Which map a page shows (ADR 0069): Google's once its key and map ID are set, MapLibre's with
 * the configured tiles otherwise, or none at all. If Google's map fails to load in a visit (its
 * key refused, its script blocked), every map goes back to MapLibre for the rest of that visit;
 * with no tiles to go back to, the map says it couldn't load.
 */
export type MapChoice = "google" | "maplibre" | "failed" | "none";

interface Setup {
  google: boolean;
  tiles: boolean;
}

const configured: Setup = {
  google: publicEnv.googleMaps !== undefined,
  tiles: publicEnv.mapTiles !== undefined,
};

/** The choice for a setup, once Google has or hasn't failed. */
export function chooseMap(setup: Setup, googleFailed: boolean): MapChoice {
  if (setup.google && !googleFailed) return "google";
  if (setup.tiles) return "maplibre";
  return setup.google ? "failed" : "none";
}

/** Whether pages get a map at all, so they can lay themselves out for one before it loads. */
export const hasAnyMap = configured.google || configured.tiles;

let googleFailed = false;
const listeners = new Set<() => void>();

/** Google's map couldn't load: every map shows the fallback from now on. */
export function reportGoogleMapsFailure(): void {
  if (googleFailed) return;
  googleFailed = true;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The map to show now; the server always renders the configured choice. */
export function useMapChoice(): MapChoice {
  return useSyncExternalStore(
    subscribe,
    () => chooseMap(configured, googleFailed),
    () => chooseMap(configured, false),
  );
}
