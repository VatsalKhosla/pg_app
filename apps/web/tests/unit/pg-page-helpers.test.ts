import { describe, expect, it } from "vitest";

import { circle } from "@/components/map/circle";
import { formatDistance } from "@/lib/format/distance";

/** Great-circle distance in metres, to check the circle's points. */
function haversine(a: [number, number], b: [number, number]): number {
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const [lng1, lat1] = a.map(toRadians) as [number, number];
  const [lng2, lat2] = b.map(toRadians) as [number, number];
  const h =
    Math.sin((lat2 - lat1) / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin((lng2 - lng1) / 2) ** 2;
  return 2 * 6_371_008.8 * Math.asin(Math.sqrt(h));
}

describe("formatDistance", () => {
  it.each([
    [3, "10 m"],
    [644, "640 m"],
    [996, "1 km"],
    [1_000, "1 km"],
    [1_249, "1.2 km"],
    [12_349, "12.3 km"],
  ])("says %d m as %s", (metres, said) => {
    expect(formatDistance(metres)).toBe(said);
  });
});

describe("circle", () => {
  it("is a closed ring whose every point is the radius away from the middle", () => {
    const middle = { lat: 28.6838, lng: 77.2112 };
    const ring = circle(middle, 150);

    expect(ring).toHaveLength(65);
    expect(ring[0]).toEqual(ring[64]);
    for (const point of ring) {
      expect(haversine([middle.lng, middle.lat], point)).toBeCloseTo(150, 3);
    }
  });
});
