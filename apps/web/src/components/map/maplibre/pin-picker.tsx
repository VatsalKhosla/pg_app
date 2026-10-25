"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { Map as MapLibreMap, Marker, NavigationControl, setWorkerUrl } from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";

import type { MapTiles } from "@/config/env";

import { type LatLng, NCR_BOUNDS, type PinPickerProps, roundCoordinate } from "../map-provider";

// The bundler emits MapLibre's worker as a hashed file of its own, under both Turbopack and
// webpack (MapLibre's guide for Next.js); MapLibre can't find it by itself once bundled.
setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());

/** Close enough to tell which building the pin is on. */
const PIN_ZOOM = 17;
const LOCALITY_ZOOM = 14;

function toLatLng(point: { lat: number; lng: number }): LatLng {
  return { lat: roundCoordinate(point.lat), lng: roundCoordinate(point.lng) };
}

function samePlace(a: LatLng, b: LatLng): boolean {
  return (
    roundCoordinate(a.lat) === roundCoordinate(b.lat) &&
    roundCoordinate(a.lng) === roundCoordinate(b.lng)
  );
}

/** The MapLibre adapter's pin picker (ADR 0023): raster tiles, one draggable default marker. */
export default function MapLibrePinPicker({
  tiles,
  value,
  onChange,
  center,
  text,
}: PinPickerProps & { tiles: MapTiles }) {
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const onChangeRef = useRef(onChange);
  const [failed, setFailed] = useState(false);
  // The map starts where the pin or the centre is when it mounts; later changes move it below.
  const initialRef = useRef({ value, center });
  const textRef = useRef(text);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // The map is made when its element mounts and removed with it (a ref callback's cleanup).
  const attach = useCallback(
    (container: HTMLDivElement | null) => {
      if (container === null) return;
      const { value: pin, center: around } = initialRef.current;
      const words = textRef.current;
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
            },
            layers: [{ id: "tiles", type: "raster", source: "tiles" }],
          },
          ...(pin !== null
            ? { center: [pin.lng, pin.lat], zoom: PIN_ZOOM }
            : around !== undefined
              ? { center: [around.lng, around.lat], zoom: LOCALITY_ZOOM }
              : {
                  bounds: [
                    [NCR_BOUNDS.west, NCR_BOUNDS.south],
                    [NCR_BOUNDS.east, NCR_BOUNDS.north],
                  ],
                }),
          maxBounds: [
            [NCR_BOUNDS.west, NCR_BOUNDS.south],
            [NCR_BOUNDS.east, NCR_BOUNDS.north],
          ],
          // One finger scrolls the page past the map on a phone; two move the map.
          cooperativeGestures: true,
          dragRotate: false,
          pitchWithRotate: false,
          touchPitch: false,
          attributionControl: { compact: true },
          locale: {
            "Map.Title": words.map,
            "Marker.Title": words.pin,
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

      const marker = new Marker({ draggable: true });
      if (pin !== null) marker.setLngLat([pin.lng, pin.lat]).addTo(map);
      marker.on("dragend", () => {
        onChangeRef.current(toLatLng(marker.getLngLat()));
      });
      map.on("click", (event) => {
        marker.setLngLat(event.lngLat);
        if (marker.getElement().parentElement === null) marker.addTo(map);
        onChangeRef.current(toLatLng(event.lngLat));
      });

      mapRef.current = map;
      markerRef.current = marker;
      return () => {
        mapRef.current = null;
        markerRef.current = null;
        map.remove();
      };
    },
    [tiles],
  );

  // A pin set outside the map (GPS, typed coordinates): move the marker there and look at it.
  // With no pin yet, look at the centre instead (a locality just chosen).
  const centerLat = center?.lat;
  const centerLng = center?.lng;
  useEffect(() => {
    const map = mapRef.current;
    const marker = markerRef.current;
    if (map === null || marker === null) return;
    if (value === null) {
      marker.remove();
      if (centerLat !== undefined && centerLng !== undefined) {
        map.easeTo({ center: [centerLng, centerLat], zoom: LOCALITY_ZOOM });
      }
      return;
    }
    const onMap = marker.getElement().parentElement !== null;
    if (onMap && samePlace(toLatLng(marker.getLngLat()), value)) return;
    marker.setLngLat([value.lng, value.lat]);
    if (!onMap) marker.addTo(map);
    map.easeTo({ center: [value.lng, value.lat], zoom: Math.max(map.getZoom(), PIN_ZOOM) });
  }, [value, centerLat, centerLng]);

  if (failed) {
    return (
      <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        {text.failed}
      </p>
    );
  }
  // MapLibre's credits link isn't underlined, and colour alone can't mark a link (WCAG 1.4.1).
  // Its styles sit outside Tailwind's layers, so only an !important rule can change them.
  return (
    <div
      ref={attach}
      className="h-72 w-full overflow-hidden rounded-md border sm:h-96 [&_.maplibregl-ctrl-attrib_a]:underline!"
    />
  );
}
