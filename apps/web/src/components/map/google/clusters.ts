import Supercluster from "supercluster";

import type { Bounds, MapPin } from "../map-provider";
import { type MapItem, mapItem, pinFeatures } from "../pin-words";
import { fromGoogleZoom, toGoogleZoom } from "./geometry";

// The MapLibre adapter's clustering, which is supercluster inside MapLibre (maplibre/map-view.tsx):
// pins within 48 px at its 512 px tiles gather into a cluster until its zoom 15, so both adapters
// cluster the same pins the same way at the same view.
const CLUSTER_RADIUS = 48;
const CLUSTER_MAX_ZOOM = 15;

interface PinProperties {
  id: string;
  label: string;
  description: string;
  verified: boolean;
  minRent: number;
}

/** What a cluster keeps of its pins: the lowest rent among them. */
interface ClusterRent {
  minRent: number;
}

export class PinClusters {
  private readonly index: Supercluster<PinProperties, ClusterRent>;

  constructor(pins: readonly MapPin[]) {
    this.index = new Supercluster<PinProperties, ClusterRent>({
      radius: CLUSTER_RADIUS,
      maxZoom: CLUSTER_MAX_ZOOM,
      map: (properties) => ({ minRent: properties.minRent }),
      reduce: (total, properties) => {
        total.minRent = Math.min(total.minRent, properties.minRent);
      },
    }).load(pinFeatures(pins));
  }

  /** The pins and clusters in `bounds` at a Google zoom. */
  items(bounds: Bounds, googleZoom: number): MapItem[] {
    const zoom = Math.max(0, Math.floor(fromGoogleZoom(googleZoom)));
    const items: MapItem[] = [];
    for (const feature of this.index.getClusters(
      [bounds.west, bounds.south, bounds.east, bounds.north],
      zoom,
    )) {
      const [lng = 0, lat = 0] = feature.geometry.coordinates;
      const item = mapItem({ ...feature.properties }, [lng, lat]);
      if (item !== null) items.push(item);
    }
    return items;
  }

  /** The Google zoom at which a cluster comes apart. */
  expansionZoom(clusterId: number): number {
    return toGoogleZoom(this.index.getClusterExpansionZoom(clusterId));
  }
}
