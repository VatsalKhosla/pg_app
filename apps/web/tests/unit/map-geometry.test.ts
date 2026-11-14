import { describe, expect, it } from "vitest";

import {
  between,
  centerBeside,
  ease,
  evenPadding,
  flight,
  fromGoogleZoom,
  nudge,
  project,
  toGoogleZoom,
  unproject,
  viewForBounds,
} from "@/components/map/google/geometry";

const SIZE = { width: 1200, height: 800 };
const LIMITS = { minZoom: 10, maxZoom: 19 };
// A fictional box in north Delhi, about 4 km by 3 km.
const BOX = { south: 28.67, west: 77.19, north: 28.7, east: 77.23 };

/** Where a point lands on a 1200 × 800 map showing `view`, in pixels from its top left. */
function onScreen(
  point: { lat: number; lng: number },
  view: { center: typeof point; zoom: number },
) {
  const scale = 256 * 2 ** view.zoom;
  const at = project(point);
  const middle = project(view.center);
  return {
    x: SIZE.width / 2 + (at.x - middle.x) * scale,
    y: SIZE.height / 2 + (at.y - middle.y) * scale,
  };
}

describe("project and unproject", () => {
  it("are each other's inverse", () => {
    const point = { lat: 28.6889, lng: 77.21 };
    const back = unproject(project(point));

    expect(back.lat).toBeCloseTo(point.lat, 9);
    expect(back.lng).toBeCloseTo(point.lng, 9);
  });

  it("put the meridian and equator in the middle of the world", () => {
    expect(project({ lat: 0, lng: 0 })).toEqual({ x: 0.5, y: 0.5 });
  });
});

describe("zoom levels", () => {
  it("run one higher on Google, whose tiles are half the size of MapLibre's", () => {
    expect(toGoogleZoom(15)).toBe(16);
    expect(fromGoogleZoom(16)).toBe(15);
  });
});

describe("viewForBounds", () => {
  it("fits the box inside the padding, touching it on the tighter side", () => {
    const view = viewForBounds(BOX, SIZE, evenPadding(24), LIMITS);
    const southWest = onScreen({ lat: BOX.south, lng: BOX.west }, view);
    const northEast = onScreen({ lat: BOX.north, lng: BOX.east }, view);

    expect(southWest.x).toBeGreaterThanOrEqual(24 - 1e-6);
    expect(northEast.x).toBeLessThanOrEqual(SIZE.width - 24 + 1e-6);
    expect(northEast.y).toBeGreaterThanOrEqual(24 - 1e-6);
    expect(southWest.y).toBeLessThanOrEqual(SIZE.height - 24 + 1e-6);
    const touches = [southWest.x - 24, SIZE.width - 24 - northEast.x, northEast.y - 24];
    expect(Math.min(...touches.map(Math.abs))).toBeLessThan(1e-6);
  });

  it("centres the box in what the list over the map leaves", () => {
    const view = viewForBounds(BOX, SIZE, { ...evenPadding(24), left: 24 + 496 }, LIMITS);
    const southWest = onScreen({ lat: BOX.south, lng: BOX.west }, view);
    const northEast = onScreen({ lat: BOX.north, lng: BOX.east }, view);

    expect((southWest.x + northEast.x) / 2).toBeCloseTo((24 + 496 + SIZE.width - 24) / 2, 6);
    expect(southWest.x).toBeGreaterThanOrEqual(520 - 1e-6);
  });

  it("keeps within the map's zoom limits", () => {
    const tiny = { south: 28.68, west: 77.2, north: 28.68, east: 77.2 };

    expect(viewForBounds(tiny, SIZE, evenPadding(24), LIMITS).zoom).toBe(19);
    expect(
      viewForBounds({ south: 27, west: 75.5, north: 30, east: 78.5 }, SIZE, evenPadding(0), LIMITS)
        .zoom,
    ).toBe(10);
  });
});

describe("centerBeside and nudge", () => {
  it("move the middle left by half what the list covers, so the point shows beside it", () => {
    const point = { lat: 28.6889, lng: 77.21 };
    const center = centerBeside(point, 15, 496);

    expect(onScreen(point, { center, zoom: 15 }).x).toBeCloseTo(SIZE.width / 2 + 248, 6);
    expect(center.lat).toBeCloseTo(point.lat, 9);
  });

  it("move a point by whole screen pixels", () => {
    const point = { lat: 28.6889, lng: 77.21 };
    const moved = nudge(point, 18, 10, -10);
    const view = { center: point, zoom: 18 };

    expect(onScreen(moved, view).x).toBeCloseTo(SIZE.width / 2 + 10, 6);
    expect(onScreen(moved, view).y).toBeCloseTo(SIZE.height / 2 - 10, 6);
  });
});

describe("between and flight", () => {
  const from = { center: { lat: 28.69, lng: 77.21 }, zoom: 15 };
  const to = { center: { lat: 28.55, lng: 77.19 }, zoom: 15.5 };

  it("start where the map is and end at the place", () => {
    const start = between(from, to, 0);
    expect(start.center.lat).toBeCloseTo(from.center.lat, 9);
    expect(start.center.lng).toBeCloseTo(from.center.lng, 9);
    expect(start.zoom).toBe(from.zoom);
    expect(between(from, to, 1).zoom).toBe(to.zoom);
    const path = flight(from, to, SIZE);
    expect(path.at(0).zoom).toBeCloseTo(from.zoom, 9);
    expect(path.at(0).center.lat).toBeCloseTo(from.center.lat, 9);
    expect(path.at(1)).toEqual(to);
  });

  it("flies out to travel far, then back in, taking longer the further it goes", () => {
    const path = flight(from, to, SIZE);
    const middle = path.at(0.5).zoom;

    expect(middle).toBeLessThan(Math.min(from.zoom, to.zoom));
    expect(path.ms).toBeGreaterThan(flight(from, between(from, to, 0.1), SIZE).ms);
  });

  it("zooms in place when the middle doesn't move", () => {
    const path = flight(from, { ...from, zoom: 17 }, SIZE);

    expect(path.at(0.5).center.lat).toBeCloseTo(from.center.lat, 9);
    expect(path.at(0.5).zoom).toBeGreaterThan(15);
    expect(path.at(0.5).zoom).toBeLessThan(17);
  });
});

describe("ease", () => {
  it("is CSS's ease: from 0 to 1, quick to start and gentle to stop", () => {
    expect(ease(0)).toBe(0);
    expect(ease(1)).toBeCloseTo(1, 6);
    expect(ease(0.5)).toBeCloseTo(0.8024, 3);
    let last = 0;
    for (let step = 1; step <= 20; step += 1) {
      const value = ease(step / 20);
      expect(value).toBeGreaterThanOrEqual(last);
      last = value;
    }
  });
});
