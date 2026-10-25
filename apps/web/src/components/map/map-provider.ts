/**
 * The map provider interface (ADR 0006, 0023). Pages and forms use these components and types
 * only; a vendor's SDK is imported inside its adapter alone, and each adapter is loaded on demand.
 *
 * `PinPicker` puts one pin on a building. Ops drag it, click or tap where it goes (so nobody has
 * to drag, WCAG 2.2 2.5.7), or move it with the arrow keys once it has focus. The search map's
 * `MapView` comes with step 3.5.
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
