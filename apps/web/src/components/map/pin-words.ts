import type { MapPin, MapViewText, ShortPrice } from "./map-provider";

/** The pins as GeoJSON points, with the properties the clustering keeps (mapItem reads them). */
export function pinFeatures(pins: readonly MapPin[]) {
  return pins.map((pin) => ({
    type: "Feature" as const,
    geometry: { type: "Point" as const, coordinates: [pin.position.lng, pin.position.lat] },
    properties: {
      id: pin.id,
      label: pin.label,
      description: pin.description,
      verified: pin.verified,
      minRent: pin.minRentPaise,
    },
  }));
}

/**
 * A pin or cluster as the search map draws it, from the clustering's GeoJSON properties. Both
 * adapters cluster with the same algorithm (supercluster, as MapLibre does inside), so their
 * features carry the same properties: `cluster`, `cluster_id` and `point_count` for a cluster,
 * the pin's own for a pin, and `minRent` on both.
 */
export type MapItem =
  | {
      kind: "pin";
      /** Stable while the pin shows, so its marker is reused rather than drawn again. */
      key: string;
      id: string;
      label: string;
      description: string;
      verified: boolean;
      lng: number;
      lat: number;
    }
  | {
      kind: "cluster";
      key: string;
      clusterId: number;
      count: number;
      minRentPaise: number;
      lng: number;
      lat: number;
    };

export function mapItem(
  properties: Record<string, unknown> | null,
  [lng, lat]: [number, number],
): MapItem | null {
  if (properties === null) return null;
  if (properties.cluster === true) {
    const clusterId = Number(properties.cluster_id);
    return {
      kind: "cluster",
      key: `cluster:${String(clusterId)}`,
      clusterId,
      count: Number(properties.point_count),
      minRentPaise: Number(properties.minRent),
      lng,
      lat,
    };
  }
  if (typeof properties.id !== "string") return null;
  return {
    kind: "pin",
    key: `pin:${properties.id}`,
    id: properties.id,
    label: String(properties.label),
    description: String(properties.description),
    verified: properties.verified === true,
    lng,
    lat,
  };
}

/**
 * What a pin or cluster shows, and its name: what it shows first, so voice control finds it by
 * that (WCAG 2.2 2.5.3), then the rest for screen readers.
 */
export function itemWords(
  item: MapItem,
  text: Pick<MapViewText, "cluster">,
  shortPrice: ShortPrice,
): { shown: string; name: string } {
  if (item.kind === "pin") {
    return { shown: item.label, name: `${item.label}, ${item.description}` };
  }
  const count = String(item.count);
  const price = shortPrice(item.minRentPaise);
  const shown = `${count} · ${price}`;
  return {
    shown,
    name: `${shown}, ${text.cluster.replace("{count}", count).replace("{price}", price)}`,
  };
}
