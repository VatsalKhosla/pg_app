"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import {
  type GeoJSONFeature,
  type GeoJSONSource,
  type LngLatBoundsLike,
  Map as MapLibreMap,
  type MapMovementEvent,
  Marker,
  NavigationControl,
  setWorkerUrl,
} from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";

import { brand } from "@/config/brand";
import type { MapTiles } from "@/config/env";

import { circle } from "../circle";
import {
  type Bounds,
  type MapPin,
  type MapPlace,
  type MapViewProps,
  NCR_BOUNDS,
  type ShortPrice,
} from "../map-provider";

// As in the pin picker: the bundler emits MapLibre's worker as a file of its own.
setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());

const MIN_ZOOM = 9;
const MAX_ZOOM = 18;
// Pins closer than this many pixels gather into a cluster, until this zoom.
const CLUSTER_RADIUS = 48;
const CLUSTER_MAX_ZOOM = 15;
const RINGS_M = [1_000, 2_000] as const;
// Room around a place the map is fitted to, in pixels.
const FIT_PADDING = 24;
// Metro stations in violet, apart from the brand's colour for campuses.
const STATION_COLOUR = "#7c3aed";
// Geo overlays come from OpenStreetMap (ADR 0020), credited beside the tiles' own credit.
const OSM_CREDIT =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const pinClasses =
  "rounded-full border bg-background px-2 py-1 text-xs font-semibold whitespace-nowrap shadow-sm outline-none transition-colors motion-reduce:transition-none focus-visible:ring-[3px] focus-visible:ring-ring/50 data-[verified=true]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground";
const clusterClasses =
  "rounded-full border-2 border-primary bg-background px-2.5 py-1.5 text-xs font-semibold whitespace-nowrap shadow-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50";

function features(pins: readonly MapPin[]) {
  return {
    type: "FeatureCollection" as const,
    features: pins.map((pin) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [pin.position.lng, pin.position.lat] },
      properties: {
        id: pin.id,
        label: pin.label,
        description: pin.description,
        verified: pin.verified,
        minRent: pin.minRentPaise,
      },
    })),
  };
}

/** The rings around the campus searched near, if any. */
function rings(campus: MapPlace | undefined) {
  return {
    type: "FeatureCollection" as const,
    features:
      campus === undefined
        ? []
        : RINGS_M.map((radius) => ({
            type: "Feature" as const,
            geometry: { type: "Polygon" as const, coordinates: [circle(campus.location, radius)] },
            properties: { radius },
          })),
  };
}

function points(places: readonly MapPlace[]) {
  return {
    type: "FeatureCollection" as const,
    features: places.map((place) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [place.location.lng, place.location.lat] },
      properties: { name: place.name },
    })),
  };
}

function lngLatBounds(bounds: Bounds): LngLatBoundsLike {
  return [
    [bounds.west, bounds.south],
    [bounds.east, bounds.north],
  ];
}

/** The campus's name beside it on the map. */
function campusLabel(map: MapLibreMap, campus: MapPlace, template: string): Marker {
  const label = document.createElement("span");
  label.className =
    "pointer-events-none rounded bg-background/90 px-1.5 py-0.5 text-[11px] font-medium text-primary shadow-sm";
  label.textContent = template.replace("{name}", campus.name);
  return new Marker({ element: label, anchor: "bottom", offset: [0, -6] })
    .setLngLat([campus.location.lng, campus.location.lat])
    .addTo(map);
}

interface Callbacks {
  onBoundsChange: MapViewProps["onBoundsChange"];
  onPinSelect: MapViewProps["onPinSelect"];
  onPinHover: MapViewProps["onPinHover"];
  shortPrice: ShortPrice;
  text: MapViewProps["text"];
}

/**
 * The MapLibre adapter's search map (ADR 0031). Pins and clusters are HTML buttons, so they take
 * focus and have names; the list beside the map gives the same results to anyone not using it.
 * A cluster shows how many PGs it holds and the lowest price among them, and zooms in when
 * pressed. Buttons outside the visible area are inert, so Tab never reaches a pin off the map.
 * Campuses are dots, many being close together; the one searched near has its name and rings.
 */
export default function MapLibreMapView({
  tiles,
  pins,
  selectedId,
  hoveredId,
  onBoundsChange,
  onPinSelect,
  onPinHover,
  campuses,
  chosenCampus,
  stations,
  initial,
  target,
  text,
  shortPrice,
}: MapViewProps & { tiles: MapTiles; shortPrice: ShortPrice }) {
  const [failed, setFailed] = useState(false);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef(new Map<string, Marker>());
  const campusLabelRef = useRef<Marker | null>(null);
  const startRef = useRef({ initial, text, campuses, stations });
  // What the map shows once its style has loaded, which is after the first effects ran.
  const shownRef = useRef({ pins, campus: campuses.find((place) => place.slug === chosenCampus) });
  const callbacksRef = useRef<Callbacks>({
    onBoundsChange,
    onPinSelect,
    onPinHover,
    shortPrice,
    text,
  });
  const highlightRef = useRef({ selectedId, hoveredId });
  // The target the map last went to; the one it started at counts.
  const targetKeyRef = useRef(target?.key ?? null);

  useEffect(() => {
    callbacksRef.current = { onBoundsChange, onPinSelect, onPinHover, shortPrice, text };
  }, [onBoundsChange, onPinSelect, onPinHover, shortPrice, text]);

  /**
   * The pins' and clusters' buttons for the pins' features MapLibre holds now: new ones added,
   * the rest brought up to date, and those it no longer holds removed.
   */
  const drawMarkers = useCallback(() => {
    const map = mapRef.current;
    if (!map?.isSourceLoaded("pins")) return;
    const source = map.getSource<GeoJSONSource>("pins");
    if (source === undefined) return;
    const shown = new Set<string>();
    for (const feature of map.querySourceFeatures("pins")) {
      const key = markerKey(feature);
      if (key === null || shown.has(key)) continue;
      shown.add(key);
      const [lng, lat] = pointOf(feature);
      const existing = markersRef.current.get(key);
      if (existing === undefined) {
        const element = document.createElement("button");
        element.type = "button";
        wire(element, feature, { source, map, callbacks: callbacksRef });
        markersRef.current.set(key, new Marker({ element }).setLngLat([lng, lat]).addTo(map));
      } else {
        describe(existing.getElement(), feature, callbacksRef.current);
        existing.setLngLat([lng, lat]);
      }
    }
    for (const [key, marker] of markersRef.current) {
      if (!shown.has(key)) {
        marker.remove();
        markersRef.current.delete(key);
      }
    }
    reachable(map, markersRef.current);
    highlight(markersRef.current, highlightRef.current);
  }, []);

  const attach = useCallback(
    (container: HTMLDivElement | null) => {
      if (container === null) return;
      const { initial: start, text: words, campuses: around, stations: metro } = startRef.current;
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
              rings: { type: "geojson", data: rings(undefined) },
              campuses: { type: "geojson", data: points(around), attribution: OSM_CREDIT },
              stations: { type: "geojson", data: points(metro), attribution: OSM_CREDIT },
              pins: {
                type: "geojson",
                data: features([]),
                cluster: true,
                clusterRadius: CLUSTER_RADIUS,
                clusterMaxZoom: CLUSTER_MAX_ZOOM,
                clusterProperties: { minRent: ["min", ["get", "minRent"]] },
              },
            },
            layers: [
              { id: "tiles", type: "raster", source: "tiles" },
              {
                id: "rings",
                type: "line",
                source: "rings",
                paint: {
                  "line-color": brand.colors.primary,
                  "line-width": 1.5,
                  "line-dasharray": [2, 2],
                },
              },
              {
                id: "campuses",
                type: "circle",
                source: "campuses",
                paint: {
                  "circle-radius": 4,
                  "circle-color": brand.colors.primary,
                  "circle-stroke-color": "#ffffff",
                  "circle-stroke-width": 1.5,
                },
              },
              {
                id: "stations",
                type: "circle",
                source: "stations",
                paint: {
                  "circle-radius": 5,
                  "circle-color": "#ffffff",
                  "circle-stroke-color": STATION_COLOUR,
                  "circle-stroke-width": 3,
                },
              },
              // Never seen: it makes MapLibre keep the pins' features, which the buttons follow.
              {
                id: "pins",
                type: "circle",
                source: "pins",
                paint: { "circle-radius": 0, "circle-opacity": 0 },
              },
            ],
          },
          bounds: lngLatBounds(start),
          fitBoundsOptions: { padding: FIT_PADDING },
          minZoom: MIN_ZOOM,
          maxZoom: MAX_ZOOM,
          maxBounds: lngLatBounds(NCR_BOUNDS),
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
      // A move the person made carries the event that started it (MapLibre's handlers and
      // controls pass it on, as the cluster buttons do); the page's own moves carry none.
      const settle = (event?: MapMovementEvent) => {
        const bounds = map.getBounds();
        callbacksRef.current.onBoundsChange(
          {
            south: bounds.getSouth(),
            west: bounds.getWest(),
            north: bounds.getNorth(),
            east: bounds.getEast(),
          },
          map.getZoom(),
          event?.originalEvent !== undefined,
        );
        drawMarkers();
      };
      map.on("load", () => {
        const { pins: shownPins, campus } = shownRef.current;
        void map.getSource<GeoJSONSource>("pins")?.setData(features(shownPins));
        void map.getSource<GeoJSONSource>("rings")?.setData(rings(campus));
        settle();
      });
      map.on("moveend", settle);
      map.on("sourcedata", (event) => {
        if (event.sourceId === "pins" && event.isSourceLoaded) drawMarkers();
      });
      mapRef.current = map;
      const markers = markersRef.current;
      return () => {
        for (const marker of markers.values()) marker.remove();
        markers.clear();
        campusLabelRef.current?.remove();
        campusLabelRef.current = null;
        mapRef.current = null;
        map.remove();
      };
    },
    [tiles, drawMarkers],
  );

  // New pins: hand them to the source, which clusters them; the buttons follow once it has.
  // Before the style has loaded there's no source yet, and the load hands them over instead.
  useEffect(() => {
    shownRef.current.pins = pins;
    void mapRef.current?.getSource<GeoJSONSource>("pins")?.setData(features(pins));
  }, [pins]);

  // The campus searched near: its rings and its name.
  useEffect(() => {
    const campus = campuses.find((place) => place.slug === chosenCampus);
    shownRef.current.campus = campus;
    const map = mapRef.current;
    if (map === null) return;
    void map.getSource<GeoJSONSource>("rings")?.setData(rings(campus));
    campusLabelRef.current?.remove();
    campusLabelRef.current = campus === undefined ? null : campusLabel(map, campus, text.campus);
  }, [campuses, chosenCampus, text.campus]);

  // A new place to show: fit it, as the page's move rather than the person's.
  useEffect(() => {
    if (target === null || target.key === targetKeyRef.current) return;
    targetKeyRef.current = target.key;
    mapRef.current?.fitBounds(lngLatBounds(target.bounds), { padding: FIT_PADDING });
  }, [target]);

  useEffect(() => {
    highlightRef.current = { selectedId, hoveredId };
    highlight(markersRef.current, highlightRef.current);
  }, [selectedId, hoveredId]);

  if (failed) {
    return (
      <p className="m-4 rounded-md border border-dashed bg-background p-4 text-sm text-muted-foreground">
        {text.failed}
      </p>
    );
  }
  return (
    <div
      ref={attach}
      className="h-full min-h-72 w-full overflow-hidden [&_.maplibregl-ctrl-attrib_a]:underline!"
    />
  );
}

function pointOf(feature: GeoJSONFeature): [number, number] {
  return (feature.geometry as unknown as { coordinates: [number, number] }).coordinates;
}

function markerKey(feature: GeoJSONFeature): string | null {
  const properties = feature.properties as Record<string, unknown>;
  if (properties.cluster === true) return `cluster:${String(properties.cluster_id)}`;
  return typeof properties.id === "string" ? `pin:${properties.id}` : null;
}

/**
 * A button's words: what it shows, then the rest for screen readers. Its name starts with what
 * it shows, so voice control finds it by that (WCAG 2.2 2.5.3).
 */
function say(button: HTMLElement, shown: string, more: string): void {
  button.textContent = shown;
  button.setAttribute("aria-label", `${shown}, ${more}`);
}

/** What a pin's or cluster's button says, which pin or cluster it is, and where. */
function describe(
  button: HTMLElement,
  feature: GeoJSONFeature,
  { shortPrice, text }: Pick<Callbacks, "shortPrice" | "text">,
): void {
  const properties = feature.properties as Record<string, unknown>;
  const [lng, lat] = pointOf(feature);
  button.dataset.lng = String(lng);
  button.dataset.lat = String(lat);
  if (properties.cluster === true) {
    const count = String(properties.point_count);
    const price = shortPrice(Number(properties.minRent));
    button.className = clusterClasses;
    say(
      button,
      `${count} · ${price}`,
      text.cluster.replace("{count}", count).replace("{price}", price),
    );
    button.dataset.clusterId = String(properties.cluster_id);
    return;
  }
  button.className = pinClasses;
  button.dataset.pinId = String(properties.id);
  button.dataset.verified = String(properties.verified === true);
  say(button, String(properties.label), String(properties.description));
}

/**
 * A new button's words and what pressing it does. It looks up what it shows when pressed, as
 * the same button may later stand for another pin or cluster at the same key.
 */
function wire(
  button: HTMLButtonElement,
  feature: GeoJSONFeature,
  {
    source,
    map,
    callbacks,
  }: { source: GeoJSONSource; map: MapLibreMap; callbacks: { current: Callbacks } },
): void {
  describe(button, feature, callbacks.current);
  button.addEventListener("click", (event) => {
    const { pinId, clusterId } = button.dataset;
    if (pinId !== undefined) {
      callbacks.current.onPinSelect(pinId);
      return;
    }
    if (clusterId === undefined) return;
    const center: [number, number] = [Number(button.dataset.lng), Number(button.dataset.lat)];
    void source.getClusterExpansionZoom(Number(clusterId)).then((zoom) => {
      map.easeTo({ center, zoom: Math.min(zoom, MAX_ZOOM) }, { originalEvent: event });
    });
  });
  const hover = (id: string | null) => {
    if (button.dataset.pinId !== undefined) callbacks.current.onPinHover(id);
  };
  button.addEventListener("mouseenter", () => {
    hover(button.dataset.pinId ?? null);
  });
  button.addEventListener("mouseleave", () => {
    hover(null);
  });
  button.addEventListener("focus", () => {
    hover(button.dataset.pinId ?? null);
  });
  button.addEventListener("blur", () => {
    hover(null);
  });
}

/** Only buttons the person can see take focus: focusing one off the map would scroll it. */
function reachable(map: MapLibreMap, markers: Map<string, Marker>): void {
  const view = map.getBounds();
  for (const marker of markers.values()) {
    marker.getElement().inert = !view.contains(marker.getLngLat());
  }
}

function highlight(
  markers: Map<string, Marker>,
  { selectedId, hoveredId }: { selectedId: string | null; hoveredId: string | null },
): void {
  for (const marker of markers.values()) {
    const element = marker.getElement();
    const id = element.dataset.pinId;
    if (id === undefined) continue;
    const active = id === selectedId || id === hoveredId;
    element.dataset.state = active ? "active" : "idle";
    element.setAttribute("aria-pressed", String(id === selectedId));
    // Above its neighbours while it's the one being looked at.
    element.style.zIndex = active ? "2" : "1";
  }
}
