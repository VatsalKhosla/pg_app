"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from "maplibre-gl";
import { useCallback, useRef, useState } from "react";

import type { MapTiles } from "@/config/env";

import { circle } from "../circle";
import { type LocationMapProps, NCR_BOUNDS } from "../map-provider";

// As in the pin picker: the bundler emits MapLibre's worker as a file of its own.
setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());

/** Close enough to see the streets around, far enough to see the whole circle. */
const AREA_ZOOM = 15;

/** The MapLibre adapter's area map: raster tiles and a soft circle, nothing to drag. */
export default function MapLibreLocationMap({
  tiles,
  center,
  radiusM,
  text,
}: LocationMapProps & { tiles: MapTiles }) {
  const [failed, setFailed] = useState(false);
  const initialRef = useRef({ center, radiusM, text });

  const attach = useCallback(
    (container: HTMLDivElement | null) => {
      if (container === null) return;
      const { center: middle, radiusM: radius, text: words } = initialRef.current;
      let map: MapLibreMap;
      try {
        map = new MapLibreMap({
          container,
          style: {
            version: 8,
            sources: {
              tiles: {
                type: "raster",
                tiles: [tiles.url],
                tileSize: 256,
                maxzoom: 19,
                attribution: tiles.attribution,
              },
              area: {
                type: "geojson",
                data: {
                  type: "Feature",
                  properties: {},
                  geometry: { type: "Polygon", coordinates: [circle(middle, radius)] },
                },
              },
            },
            layers: [
              { id: "tiles", type: "raster", source: "tiles" },
              {
                id: "area-fill",
                type: "fill",
                source: "area",
                paint: { "fill-color": "#0e6b74", "fill-opacity": 0.18 },
              },
              {
                id: "area-line",
                type: "line",
                source: "area",
                paint: { "line-color": "#0e6b74", "line-width": 2 },
              },
            ],
          },
          center: [middle.lng, middle.lat],
          zoom: AREA_ZOOM,
          maxBounds: [
            [NCR_BOUNDS.west, NCR_BOUNDS.south],
            [NCR_BOUNDS.east, NCR_BOUNDS.north],
          ],
          cooperativeGestures: true,
          dragRotate: false,
          pitchWithRotate: false,
          touchPitch: false,
          attributionControl: { compact: true },
          locale: {
            "Map.Title": words.map,
            "NavigationControl.ZoomIn": words.zoomIn,
            "NavigationControl.ZoomOut": words.zoomOut,
            "AttributionControl.ToggleAttribution": words.credits,
            "CooperativeGesturesHandler.MobileHelpText": words.twoFingers,
            "CooperativeGesturesHandler.WindowsHelpText": words.ctrlScroll,
            "CooperativeGesturesHandler.MacHelpText": words.cmdScroll,
          },
        });
      } catch {
        // MapLibre needs WebGL 2.
        setFailed(true);
        return;
      }
      map.touchZoomRotate.disableRotation();
      map.keyboard.disableRotation();
      map.addControl(new NavigationControl({ showCompass: false }), "top-right");
      return () => {
        map.remove();
      };
    },
    [tiles],
  );

  if (failed) {
    return (
      <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        {text.failed}
      </p>
    );
  }
  return (
    <div
      ref={attach}
      className="h-64 w-full overflow-hidden rounded-md border [&_.maplibregl-ctrl-attrib_a]:underline!"
    />
  );
}
