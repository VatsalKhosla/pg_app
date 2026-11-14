import type { Bounds, LatLng } from "../map-provider";

/**
 * Web Mercator arithmetic for the Google adapter's own camera moves (ADR 0069), kept free of the
 * SDK so it can be tested. Google's map is 256 px wide at zoom 0.
 */
const TILE_PX = 256;

/**
 * Google counts zoom in 256 px tiles and MapLibre in 512 px ones, so the same view is one level
 * higher on Google. The map interface speaks MapLibre's zoom (the search API's `zoom` included).
 */
export const ZOOM_OFFSET = 1;

export function toGoogleZoom(zoom: number): number {
  return zoom + ZOOM_OFFSET;
}

export function fromGoogleZoom(zoom: number): number {
  return zoom - ZOOM_OFFSET;
}

/** A point on the world as a fraction of its width and height: 0 to 1, north-west first. */
export interface WorldPoint {
  x: number;
  y: number;
}

export function project({ lat, lng }: LatLng): WorldPoint {
  const sin = Math.sin((lat * Math.PI) / 180);
  return {
    x: (lng + 180) / 360,
    y: 0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI),
  };
}

export function unproject({ x, y }: WorldPoint): LatLng {
  return {
    lat: (Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180) / Math.PI,
    lng: x * 360 - 180,
  };
}

function worldPx(zoom: number): number {
  return TILE_PX * 2 ** zoom;
}

export interface View {
  center: LatLng;
  zoom: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface Padding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export function evenPadding(pixels: number): Padding {
  return { top: pixels, right: pixels, bottom: pixels, left: pixels };
}

/**
 * The view that shows `bounds` whole inside the map, kept `padding` pixels in from its edges and
 * centred in what's left, at a fractional zoom within `limits`: Google's fitBounds, worked out
 * beforehand so the map can glide there instead of jumping.
 */
export function viewForBounds(
  bounds: Bounds,
  size: Size,
  padding: Padding,
  limits: { minZoom: number; maxZoom: number },
): View {
  const southWest = project({ lat: bounds.south, lng: bounds.west });
  const northEast = project({ lat: bounds.north, lng: bounds.east });
  const spanX = Math.abs(northEast.x - southWest.x);
  const spanY = Math.abs(southWest.y - northEast.y);
  const width = Math.max(1, size.width - padding.left - padding.right);
  const height = Math.max(1, size.height - padding.top - padding.bottom);
  const fit = Math.log2(Math.min(width / (spanX * TILE_PX), height / (spanY * TILE_PX)));
  const zoom = Math.min(limits.maxZoom, Math.max(limits.minZoom, Number.isFinite(fit) ? fit : 99));
  const scale = worldPx(zoom);
  return {
    center: unproject({
      x: (southWest.x + northEast.x) / 2 - (padding.left - padding.right) / 2 / scale,
      y: (southWest.y + northEast.y) / 2 - (padding.top - padding.bottom) / 2 / scale,
    }),
    zoom,
  };
}

/**
 * The map's middle that shows `point` in the middle of the part people can see, when the left
 * `insetLeft` pixels are covered (by the floating list): what MapLibre's padding does.
 */
export function centerBeside(point: LatLng, zoom: number, insetLeft: number): LatLng {
  return nudge(point, zoom, -insetLeft / 2, 0);
}

/** A view part of the way to another: the middle in a straight line on the map, the zoom evenly. */
export function between(from: View, to: View, k: number): View {
  const start = project(from.center);
  const end = project(to.center);
  return {
    center: unproject({ x: start.x + (end.x - start.x) * k, y: start.y + (end.y - start.y) * k }),
    zoom: from.zoom + (to.zoom - from.zoom) * k,
  };
}

/**
 * A flight from one view to another along van Wijk and Nuij's path ("Smooth and efficient zooming
 * and panning", 2003), as MapLibre's flyTo flies: out while it travels, then in. `at(k)` is the
 * view at progress k (0 to 1); `ms` is how long it takes at MapLibre's default speed.
 */
export function flight(from: View, to: View, size: Size): { ms: number; at: (k: number) => View } {
  const rho = 1.42;
  const speed = 1.2;
  const rho2 = rho * rho;
  const start = project(from.center);
  const end = project(to.center);
  const w0 = Math.max(size.width, size.height);
  const w1 = w0 / 2 ** (to.zoom - from.zoom);
  // How far the middle travels, in pixels at the starting zoom.
  const u1 = Math.hypot(end.x - start.x, end.y - start.y) * worldPx(from.zoom);
  const r = (i: 0 | 1) => {
    const b =
      (w1 * w1 - w0 * w0 + (i === 1 ? -1 : 1) * rho2 * rho2 * u1 * u1) /
      (2 * (i === 1 ? w1 : w0) * rho2 * u1);
    return Math.log(Math.sqrt(b * b + 1) - b);
  };
  const r0 = r(0);
  let width = (s: number) => Math.cosh(r0) / Math.cosh(r0 + rho * s);
  let travelled = (s: number) =>
    (w0 * ((Math.cosh(r0) * Math.tanh(r0 + rho * s) - Math.sinh(r0)) / rho2)) / u1;
  let length = (r(1) - r0) / rho;
  if (Math.abs(u1) < 1e-6 || !Number.isFinite(length)) {
    // Zooming in place: no path to bend.
    const direction = w1 < w0 ? -1 : 1;
    length = Math.abs(Math.log(w1 / w0)) / rho;
    travelled = () => 0;
    width = (s: number) => Math.exp(direction * rho * s);
  }
  return {
    ms: (1000 * length) / speed,
    at: (k: number) => {
      if (k >= 1) return to;
      const s = k * length;
      const along = travelled(s);
      return {
        center: unproject({
          x: start.x + (end.x - start.x) * along,
          y: start.y + (end.y - start.y) * along,
        }),
        zoom: from.zoom + Math.log2(1 / width(s)),
      };
    },
  };
}

/**
 * CSS's `ease` (cubic-bezier(0.25, 0.1, 0.25, 1)), MapLibre's default for camera moves: the
 * curve's x solved for t by Newton's method, falling back to bisection.
 */
export function ease(progress: number): number {
  const [x1, y1, x2, y2] = [0.25, 0.1, 0.25, 1];
  const cx = 3 * x1;
  const bx = 3 * (x2 - x1) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * y1;
  const by = 3 * (y2 - y1) - cy;
  const ay = 1 - cy - by;
  const curveX = (t: number) => ((ax * t + bx) * t + cx) * t;
  const slopeX = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  const x = Math.min(1, Math.max(0, progress));
  let t = x;
  for (let step = 0; step < 8; step += 1) {
    const error = curveX(t) - x;
    if (Math.abs(error) < 1e-6) return ((ay * t + by) * t + cy) * t;
    const slope = slopeX(t);
    if (Math.abs(slope) < 1e-6) break;
    t -= error / slope;
  }
  let low = 0;
  let high = 1;
  t = x;
  while (high - low > 1e-6) {
    if (curveX(t) < x) low = t;
    else high = t;
    t = (low + high) / 2;
  }
  return ((ay * t + by) * t + cy) * t;
}

/** `point` moved by a number of screen pixels at `zoom`, on a map that's neither tilted nor turned. */
export function nudge(point: LatLng, zoom: number, dx: number, dy: number): LatLng {
  const world = project(point);
  const scale = worldPx(zoom);
  return unproject({ x: world.x + dx / scale, y: world.y + dy / scale });
}
