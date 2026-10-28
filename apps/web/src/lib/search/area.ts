import type { Bounds, LatLng } from "@/components/map/map-provider";

/**
 * Map areas for search: around a campus or a locality, around every campus, and the `bbox`
 * parameter the API takes (west,south,east,north in degrees).
 */

const METRES_PER_DEGREE = 111_320;
// Five decimal places is about a metre: as fine as a map area needs, and short in a URL.
const BBOX_DECIMALS = 5;

/** A square around a point, `radiusM` from it on each side. */
export function around(center: LatLng, radiusM: number): Bounds {
  const dLat = radiusM / METRES_PER_DEGREE;
  const dLng = radiusM / (METRES_PER_DEGREE * Math.cos((center.lat * Math.PI) / 180));
  return {
    south: center.lat - dLat,
    west: center.lng - dLng,
    north: center.lat + dLat,
    east: center.lng + dLng,
  };
}

/** The smallest area holding every point, `marginM` wider each way; null for no points. */
export function enclosing(points: readonly LatLng[], marginM: number): Bounds | null {
  const [first, ...rest] = points;
  if (first === undefined) return null;
  let box = around(first, marginM);
  for (const point of rest) {
    const next = around(point, marginM);
    box = {
      south: Math.min(box.south, next.south),
      west: Math.min(box.west, next.west),
      north: Math.max(box.north, next.north),
      east: Math.max(box.east, next.east),
    };
  }
  return box;
}

export function bboxParam(bounds: Bounds): string {
  return [bounds.west, bounds.south, bounds.east, bounds.north]
    .map((value) => value.toFixed(BBOX_DECIMALS))
    .join(",");
}

/** A `bbox` parameter back as an area, or null if it isn't four numbers in the right order. */
export function parseBbox(text: string | null | undefined): Bounds | null {
  if (text === undefined || text === null) return null;
  const values = text.split(",").map(Number);
  if (values.length !== 4 || values.some((value) => !Number.isFinite(value))) return null;
  const [west, south, east, north] = values as [number, number, number, number];
  if (west >= east || south >= north) return null;
  return { south, west, north, east };
}
