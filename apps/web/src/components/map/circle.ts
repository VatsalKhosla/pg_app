import type { LatLng } from "./map-provider";

const EARTH_RADIUS_M = 6_371_008.8;

/** A circle on the ground as a polygon ring: `radiusM` around `center`, in 64 steps, closed. */
export function circle(center: LatLng, radiusM: number): [number, number][] {
  const angular = radiusM / EARTH_RADIUS_M;
  const lat = (center.lat * Math.PI) / 180;
  const lng = (center.lng * Math.PI) / 180;
  const ring: [number, number][] = [];
  for (let step = 0; step <= 64; step += 1) {
    const bearing = (step / 64) * 2 * Math.PI;
    const pointLat = Math.asin(
      Math.sin(lat) * Math.cos(angular) + Math.cos(lat) * Math.sin(angular) * Math.cos(bearing),
    );
    const pointLng =
      lng +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angular) * Math.cos(lat),
        Math.cos(angular) - Math.sin(lat) * Math.sin(pointLat),
      );
    ring.push([(pointLng * 180) / Math.PI, (pointLat * 180) / Math.PI]);
  }
  return ring;
}
