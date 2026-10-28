/**
 * The map provider interface (ADR 0006, 0023). Pages and forms use these components and types
 * only; a vendor's SDK is imported inside its adapter alone, and each adapter is loaded on demand.
 *
 * `PinPicker` puts one pin on a building. Ops drag it, click or tap where it goes (so nobody has
 * to drag, WCAG 2.2 2.5.7), or move it with the arrow keys once it has focus. `LocationMap` shows
 * a PG's approximate area on its page (step 3.4): a circle around the display point, never a pin.
 * `MapView` is the search map (step 3.5): price pins that cluster, campuses (with rings around the
 * one searched near) and metro stations, locked to NCR.
 */

export interface LatLng {
  lat: number;
  lng: number;
}

export interface Bounds {
  south: number;
  west: number;
  north: number;
  east: number;
}

/**
 * Delhi NCR with room to spare: the box the API checks pins against (NCR_BOUNDS in
 * apps/api/src/app/core/geometry.py). The map doesn't pan past it.
 */
export const NCR_BOUNDS: Bounds = { south: 27.0, west: 75.5, north: 30.0, east: 78.5 };

/** Everything the map says, translated by the page. */
export interface PinPickerText {
  /** What the map is for, for screen readers. */
  map: string;
  /** The pin's name, for screen readers: say that the arrow keys move it. */
  pin: string;
  zoomIn: string;
  zoomOut: string;
  /** The button that shows the tiles' credits. */
  credits: string;
  /** Map gestures leave the page's scrolling alone: this is how to pan instead. */
  twoFingers: string;
  ctrlScroll: string;
  cmdScroll: string;
  /** Shown if the map can't start (no WebGL, say); the coordinate fields still work. */
  failed: string;
}

export interface PinPickerProps {
  /** The pin, or null before it's placed. */
  value: LatLng | null;
  onChange: (value: LatLng) => void;
  /** Where to look while there's no pin (the locality's centre); all of NCR without one. */
  center?: LatLng | undefined;
  text: PinPickerText;
}

/** Pins keep 6 decimal places, about 10 cm: finer than any phone's GPS. */
export function roundCoordinate(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

/** What the area map says, translated by the page. */
export interface LocationMapText {
  /** What the map shows, for screen readers: the page also says it in words. */
  map: string;
  zoomIn: string;
  zoomOut: string;
  credits: string;
  twoFingers: string;
  ctrlScroll: string;
  cmdScroll: string;
  failed: string;
}

export interface LocationMapProps {
  /** The display point (ADR 0021): the building is somewhere within the circle. */
  center: LatLng;
  radiusM: number;
  text: LocationMapText;
}

/** One listing on the search map, at its display point. */
export interface MapPin {
  id: string;
  position: LatLng;
  /** What the pin shows: "₹8k–12k". */
  label: string;
  /** What a screen reader hears after the label: the full prices and who it's for. */
  description: string;
  verified: boolean;
  /** The lowest rent, so a cluster can show its lowest. */
  minRentPaise: number;
}

export interface MapPlace {
  slug: string;
  name: string;
  location: LatLng;
}

export interface MapViewText {
  map: string;
  zoomIn: string;
  zoomOut: string;
  credits: string;
  twoFingers: string;
  ctrlScroll: string;
  cmdScroll: string;
  failed: string;
  /** What a screen reader hears for a cluster, with {count} and {price} (its lowest). */
  cluster: string;
  /** The chosen campus's label, with {name}. */
  campus: string;
}

export interface MapViewProps {
  /** Pins are buttons with a `data-pin-id`, so the page can give one focus back. */
  pins: readonly MapPin[];
  selectedId: string | null;
  hoveredId: string | null;
  /**
   * The map came to rest: its area and zoom, and whether the person moved it (dragging, zooming,
   * the keys, a cluster) rather than the page (loading, or showing a place it was given).
   */
  onBoundsChange: (bounds: Bounds, zoom: number, byPerson: boolean) => void;
  onPinSelect: (id: string) => void;
  onPinHover: (id: string | null) => void;
  campuses: readonly MapPlace[];
  /** The campus searched near, by slug: its name and its 1 and 2 km rings show. */
  chosenCampus: string | null;
  stations: readonly MapPlace[];
  /** Where to look first. */
  initial: Bounds;
  /** A place to show, such as a campus just chosen: the map goes there whenever its key changes. */
  target: { key: string; bounds: Bounds } | null;
  text: MapViewText;
}

/** Turns a cluster's price into its label; the adapter doesn't format money itself. */
export type ShortPrice = (paise: number) => string;
