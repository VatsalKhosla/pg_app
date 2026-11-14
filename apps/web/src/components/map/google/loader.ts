/// <reference types="google.maps" />
import { importLibrary, setOptions } from "@googlemaps/js-api-loader";

import type { GoogleMapsConfig } from "@/config/env";

import { reportGoogleMapsFailure } from "../choice";
import { cooperative, type MapPlacement } from "../gestures";
import { NCR_BOUNDS } from "../map-provider";

declare global {
  interface Window {
    /** Google calls this when it refuses the key: wrong site, API not enabled, or no billing. */
    gm_authFailure?: () => void;
  }
}

export interface GoogleLibraries {
  core: google.maps.CoreLibrary;
  maps: google.maps.MapsLibrary;
  marker: google.maps.MarkerLibrary;
}

let loading: Promise<GoogleLibraries> | undefined;

/**
 * Google's map script, loaded once per visit and only where a map shows (ADR 0069). Its loader
 * adds the script with the page's CSP nonce, and 'strict-dynamic' lets it load the rest. India's
 * region gives India's official boundaries. If the script can't load, or Google refuses the key
 * later, every map goes back to MapLibre (choice.ts).
 */
export function loadGoogleMaps(config: GoogleMapsConfig): Promise<GoogleLibraries> {
  loading ??= load(config);
  return loading;
}

async function load(config: GoogleMapsConfig): Promise<GoogleLibraries> {
  window.gm_authFailure = reportGoogleMapsFailure;
  setOptions({
    key: config.apiKey,
    v: "weekly",
    region: "IN",
    language: "en",
    mapIds: [config.mapId],
  });
  try {
    const [core, maps, marker] = await Promise.all([
      importLibrary("core"),
      importLibrary("maps"),
      importLibrary("marker"),
    ]);
    return { core, maps, marker };
  } catch (error) {
    reportGoogleMapsFailure();
    throw error;
  }
}

/** Whether the page is drawn dark: the visitor's choice in the header, else their system's. */
function pageIsDark(): boolean {
  const theme = document.documentElement.dataset.theme;
  if (theme === "dark" || theme === "light") return theme === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * What every Google map here shares: the vector map of the configured map ID (which HTML pins
 * need), in the page's light or dark, locked to NCR, with no rotating or tilting by hand, none of
 * Google's own buttons (the adapter draws its own zoom buttons, in the page's words) and gestures
 * as gestures.ts says.
 */
export function baseOptions(
  libraries: GoogleLibraries,
  config: GoogleMapsConfig,
  placement: MapPlacement,
): google.maps.MapOptions {
  return {
    mapId: config.mapId,
    renderingType: libraries.maps.RenderingType.VECTOR,
    colorScheme: pageIsDark() ? libraries.core.ColorScheme.DARK : libraries.core.ColorScheme.LIGHT,
    gestureHandling: cooperative(placement) ? "cooperative" : "greedy",
    disableDefaultUI: true,
    clickableIcons: false,
    keyboardShortcuts: true,
    tiltInteractionEnabled: false,
    headingInteractionEnabled: false,
    restriction: { latLngBounds: NCR_BOUNDS, strictBounds: false },
  };
}

/** Whether the map draws vectors: Google falls back to raster where WebGL can't run it. */
export function isVector(map: google.maps.Map): boolean {
  return map.getRenderingType() === "VECTOR";
}

/**
 * Names the map for screen readers in the page's words: Google's map is a region it calls "Map",
 * as MapLibre's canvas is until its title is set.
 */
export function nameMap(container: HTMLElement, name: string): void {
  container.querySelector('[role="region"]')?.setAttribute("aria-label", name);
}
