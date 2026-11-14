import { describe, expect, it } from "vitest";

import { PinClusters } from "@/components/map/google/clusters";
import type { MapPin } from "@/components/map/map-provider";
import { itemWords, mapItem } from "@/components/map/pin-words";

const text = { cluster: "{count} PGs here, from {price} a month: zoom in" };
const shortPrice = (paise: number) => `₹${String(Math.round(paise / 100_000))}k`;

/** Fictional pins: three a few metres apart, and one across town. */
function pins(): MapPin[] {
  const pin = (id: string, lat: number, lng: number, minRentPaise: number): MapPin => ({
    id,
    position: { lat, lng },
    label: `₹${String(minRentPaise / 100_000)}k`,
    description: `${id}, for girls`,
    verified: id !== "c",
    minRentPaise,
  });
  return [
    pin("a", 28.6889, 77.21, 900_000),
    pin("b", 28.6891, 77.2102, 750_000),
    pin("c", 28.6893, 77.2098, 1_200_000),
    pin("far", 28.55, 77.25, 600_000),
  ];
}

const DELHI = { south: 28.4, west: 76.9, north: 28.9, east: 77.5 };

describe("mapItem and itemWords", () => {
  it("names a pin by what it shows, then the rest", () => {
    const item = mapItem(
      {
        id: "a",
        label: "₹9k–12k",
        description: "₹9,000 to ₹12,000 a month, Girls",
        verified: true,
        minRent: 900_000,
      },
      [77.21, 28.6889],
    );

    expect(item).toMatchObject({ kind: "pin", key: "pin:a", id: "a", verified: true });
    if (item === null) throw new Error("no item");
    expect(itemWords(item, text, shortPrice)).toEqual({
      shown: "₹9k–12k",
      name: "₹9k–12k, ₹9,000 to ₹12,000 a month, Girls",
    });
  });

  it("names a cluster by its count and lowest price", () => {
    const item = mapItem(
      { cluster: true, cluster_id: 33, point_count: 3, minRent: 750_000 },
      [77.21, 28.69],
    );

    expect(item).toMatchObject({ kind: "cluster", key: "cluster:33", count: 3 });
    if (item === null) throw new Error("no item");
    expect(itemWords(item, text, shortPrice)).toEqual({
      shown: "3 · ₹8k",
      name: "3 · ₹8k, 3 PGs here, from ₹8k a month: zoom in",
    });
  });

  it("skips what isn't a pin or a cluster", () => {
    expect(mapItem({ name: "a campus" }, [77.21, 28.69])).toBeNull();
    expect(mapItem(null, [77.21, 28.69])).toBeNull();
  });
});

describe("PinClusters", () => {
  it("gathers close pins into one cluster with the lowest rent among them", () => {
    const items = new PinClusters(pins()).items(DELHI, 12);
    const cluster = items.find((item) => item.kind === "cluster");

    expect(cluster).toMatchObject({ count: 3, minRentPaise: 750_000 });
    expect(items.filter((item) => item.kind === "pin").map((item) => item.key)).toEqual([
      "pin:far",
    ]);
  });

  it("shows every pin once zoomed past MapLibre's last clustered zoom", () => {
    const items = new PinClusters(pins()).items(DELHI, toGoogle(16));

    expect(items.every((item) => item.kind === "pin")).toBe(true);
    expect(items).toHaveLength(4);
  });

  it("says, in Google's zoom, where a cluster comes apart", () => {
    const clusters = new PinClusters(pins());
    const cluster = clusters.items(DELHI, 12).find((item) => item.kind === "cluster");
    if (cluster?.kind !== "cluster") throw new Error("no cluster");

    const zoom = clusters.expansionZoom(cluster.clusterId);
    expect(zoom).toBeGreaterThan(12);
    expect(
      clusters.items(DELHI, zoom).some((item) => item.kind === "cluster" && item.count === 3),
    ).toBe(false);
  });
});

function toGoogle(zoom: number): number {
  return zoom + 1;
}
