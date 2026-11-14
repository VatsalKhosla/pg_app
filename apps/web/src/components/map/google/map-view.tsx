"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { brand } from "@/config/brand";
import type { GoogleMapsConfig } from "@/config/env";

import { reportGoogleMapsFailure } from "../choice";
import { circle } from "../circle";
import type { Bounds, MapPlace, MapViewProps, ShortPrice } from "../map-provider";
import { itemWords, type MapItem } from "../pin-words";
import { TiltButton } from "../tilt-button";
import { Camera } from "./camera";
import { PinClusters } from "./clusters";
import { centerBeside, evenPadding, fromGoogleZoom, toGoogleZoom, viewForBounds } from "./geometry";
import { baseOptions, type GoogleLibraries, isVector, loadGoogleMaps, nameMap } from "./loader";
import { PersonWatch } from "./person";
import { ZoomButtons } from "./zoom-buttons";

// The MapLibre adapter's limits and views, in Google's zoom (geometry.ts).
const MIN_ZOOM = toGoogleZoom(9);
const MAX_ZOOM = toGoogleZoom(18);
const RINGS_M = [1_000, 2_000] as const;
const FIT_PADDING = 24;
const STATION_COLOUR = brand.colors.marigold;
// Tipped back and turned a little, as on MapLibre; Google allows less tilt further out.
const TILT = 58;
const HEADING = -14;
const TILT_MS = 900;
// How long a cluster's zoom and a zoom button's step take, as MapLibre's easeTo.
const STEP_MS = 500;
// Pins and clusters are kept this share of the view past each edge, so a pan finds them there.
const MARGIN = 0.25;
const OSM_COPYRIGHT = "https://www.openstreetmap.org/copyright";

// The marker is the button (Google's own clickable marker, which takes focus, Enter and the
// arrow keys between pins); its face shows the price, styled from the marker's state.
const faceBase =
  "block whitespace-nowrap text-xs font-bold text-card-foreground transition-[background-color,color,border-color,scale,box-shadow] duration-(--duration-fast) ease-standard group-hover/pin:scale-105 group-focus-visible/pin:ring-2 group-focus-visible/pin:ring-ring group-focus-visible/pin:ring-offset-2 group-focus-visible/pin:ring-offset-background motion-reduce:transition-none motion-reduce:group-hover/pin:scale-100";
const pinFace = `${faceBase} min-h-7 rounded-full border border-input bg-card px-2.5 py-1 shadow-md group-hover/pin:border-foreground group-data-[verified=true]/pin:border-primary group-data-[state=active]/pin:scale-105 group-data-[state=active]/pin:border-primary group-data-[state=active]/pin:bg-primary group-data-[state=active]/pin:text-primary-foreground group-data-[state=active]/pin:shadow-lg`;
const clusterFace = `${faceBase} min-h-8 rounded-full border-2 border-primary bg-card px-3 py-1.5 shadow-lg`;

type AdvancedMarker = google.maps.marker.AdvancedMarkerElement;

interface Callbacks {
  onBoundsChange: MapViewProps["onBoundsChange"];
  onPinSelect: MapViewProps["onPinSelect"];
  onPinHover: MapViewProps["onPinHover"];
  shortPrice: ShortPrice;
  text: MapViewProps["text"];
}

/** Everything drawn on one map, so it can all be taken off again. */
interface Drawn {
  map: google.maps.Map;
  libraries: GoogleLibraries;
  camera: Camera;
  person: PersonWatch;
  markers: Map<string, { marker: AdvancedMarker; face: HTMLElement }>;
  rings: google.maps.Polyline[];
  label: AdvancedMarker | null;
}

function boundsOf(bounds: google.maps.LatLngBounds): Bounds {
  const northEast = bounds.getNorthEast();
  const southWest = bounds.getSouthWest();
  return {
    south: southWest.lat(),
    west: southWest.lng(),
    north: northEast.lat(),
    east: northEast.lng(),
  };
}

function widen(bounds: Bounds, share: number): Bounds {
  const lat = (bounds.north - bounds.south) * share;
  const lng = (bounds.east - bounds.west) * share;
  return {
    south: bounds.south - lat,
    west: bounds.west - lng,
    north: bounds.north + lat,
    east: bounds.east + lng,
  };
}

/** A dot for a campus or a metro station, as MapLibre's circle layers draw them. */
function dot(
  libraries: GoogleLibraries,
  map: google.maps.Map,
  place: MapPlace,
  style: Record<string, string>,
): AdvancedMarker {
  const face = document.createElement("span");
  Object.assign(face.style, {
    display: "block",
    boxSizing: "content-box",
    borderRadius: "9999px",
    pointerEvents: "none",
    ...style,
  });
  const marker = new libraries.marker.AdvancedMarkerElement({
    position: place.location,
    anchorLeft: "-50%",
    anchorTop: "-50%",
    zIndex: 0,
  });
  marker.append(face);
  marker.map = map;
  return marker;
}

/**
 * The Google adapter's search map (ADR 0069): the same pins, clusters, campuses, rings and
 * stations as MapLibre's (ADR 0031), on Google's vector map. Pins and clusters are Google's
 * clickable HTML markers, named and marked as MapLibre's buttons are (`data-pin-id`,
 * `data-state`, `aria-pressed`); Tab reaches the first and the arrow keys the rest of those in
 * view. Clusters are supercluster's, with MapLibre's settings, so both maps group pins alike.
 */
export default function GoogleMapView({
  config,
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
  insetLeft = 0,
}: MapViewProps & { config: GoogleMapsConfig; shortPrice: ShortPrice }) {
  const [tilted, setTilted] = useState(false);
  const [vector, setVector] = useState(false);
  const [limits, setLimits] = useState({ atMin: false, atMax: false });
  const drawnRef = useRef<Drawn | null>(null);
  const startRef = useRef({ initial, campuses, stations });
  const clustersRef = useRef(new PinClusters(pins));
  const campusRef = useRef(campuses.find((place) => place.slug === chosenCampus));
  const callbacksRef = useRef<Callbacks>({
    onBoundsChange,
    onPinSelect,
    onPinHover,
    shortPrice,
    text,
  });
  const highlightRef = useRef({ selectedId, hoveredId });
  const insetRef = useRef(insetLeft);
  // The target the map last went to; the one it started at counts.
  const targetKeyRef = useRef(target?.key ?? null);
  const targetRef = useRef(target);

  useEffect(() => {
    callbacksRef.current = { onBoundsChange, onPinSelect, onPinHover, shortPrice, text };
  }, [onBoundsChange, onPinSelect, onPinHover, shortPrice, text]);

  /** Pins and clusters for the view and a margin around it: new ones added, gone ones removed. */
  const drawMarkers = useCallback(() => {
    const drawn = drawnRef.current;
    const view = drawn?.map.getBounds();
    const zoom = drawn?.map.getZoom();
    if (drawn === null || view === undefined || zoom === undefined) return;
    const shown = new Set<string>();
    for (const item of clustersRef.current.items(widen(boundsOf(view), MARGIN), zoom)) {
      if (shown.has(item.key)) continue;
      shown.add(item.key);
      const existing = drawn.markers.get(item.key);
      if (existing === undefined) {
        drawn.markers.set(item.key, addMarker(drawn, item));
      } else {
        describe(existing, item, callbacksRef.current);
      }
    }
    for (const [key, { marker }] of drawn.markers) {
      if (!shown.has(key)) {
        marker.map = null;
        drawn.markers.delete(key);
      }
    }
    highlight(drawn.markers, highlightRef.current);

    function addMarker(on: Drawn, item: MapItem) {
      const face = document.createElement("span");
      const marker = new on.libraries.marker.AdvancedMarkerElement({
        gmpClickable: true,
        anchorLeft: "-50%",
        anchorTop: "-50%",
        zIndex: 1,
      });
      marker.classList.add("group/pin");
      marker.style.outline = "none";
      marker.append(face);
      const entry = { marker, face };
      describe(entry, item, callbacksRef.current);
      marker.addEventListener("gmp-click", () => {
        const { pinId, clusterId, lat, lng } = marker.dataset;
        if (pinId !== undefined) {
          callbacksRef.current.onPinSelect(pinId);
          return;
        }
        if (clusterId === undefined) return;
        const next = Math.min(clustersRef.current.expansionZoom(Number(clusterId)), MAX_ZOOM);
        on.person.mark();
        on.camera.ease(
          {
            center: centerBeside({ lat: Number(lat), lng: Number(lng) }, next, insetRef.current),
            zoom: next,
          },
          STEP_MS,
        );
      });
      const hover = (id: string | null) => {
        if (marker.dataset.pinId !== undefined) callbacksRef.current.onPinHover(id);
      };
      marker.addEventListener("mouseenter", () => {
        hover(marker.dataset.pinId ?? null);
      });
      marker.addEventListener("mouseleave", () => {
        hover(null);
      });
      marker.addEventListener("focus", () => {
        hover(marker.dataset.pinId ?? null);
      });
      marker.addEventListener("blur", () => {
        hover(null);
      });
      marker.map = on.map;
      return entry;
    }
  }, []);

  const showCampus = useCallback((drawn: Drawn, campus: MapPlace | undefined) => {
    for (const ring of drawn.rings) ring.setMap(null);
    drawn.rings = [];
    if (drawn.label !== null) drawn.label.map = null;
    drawn.label = null;
    if (campus === undefined) return;
    drawn.rings = RINGS_M.map(
      (radius) =>
        new drawn.libraries.maps.Polyline({
          map: drawn.map,
          path: circle(campus.location, radius).map(([lng, lat]) => ({ lat, lng })),
          clickable: false,
          strokeOpacity: 0,
          // A dashed line, as MapLibre's rings: a short stroke repeated along the ring.
          icons: [
            {
              icon: {
                path: "M 0,-1 0,1",
                strokeColor: brand.colors.primary,
                strokeOpacity: 1,
                strokeWeight: 1.5,
                scale: 1.5,
              },
              offset: "0",
              repeat: "6px",
            },
          ],
        }),
    );
    const words = document.createElement("span");
    words.className =
      "pointer-events-none mb-1.5 block rounded-full border border-primary/30 bg-background/95 px-2.5 py-0.5 text-[11px] font-semibold text-primary shadow-sm backdrop-blur-xs";
    words.textContent = callbacksRef.current.text.campus.replace("{name}", campus.name);
    const label = new drawn.libraries.marker.AdvancedMarkerElement({
      position: campus.location,
      zIndex: 3,
    });
    label.append(words);
    label.map = drawn.map;
    drawn.label = label;
  }, []);

  const goToTarget = useCallback((drawn: Drawn) => {
    const next = targetRef.current;
    if (next === null || next.key === targetKeyRef.current) return;
    targetKeyRef.current = next.key;
    const element = drawn.map.getDiv();
    const size = { width: element.clientWidth, height: element.clientHeight };
    const view = viewForBounds(
      next.bounds,
      size,
      { ...evenPadding(FIT_PADDING), left: FIT_PADDING + insetRef.current },
      { minZoom: MIN_ZOOM, maxZoom: MAX_ZOOM },
    );
    drawn.camera.fly(view, size);
  }, []);

  const attach = useCallback(
    (container: HTMLDivElement | null) => {
      if (container === null) return;
      let disposed = false;
      let detach: (() => void) | null = null;
      loadGoogleMaps(config).then(
        (libraries) => {
          if (disposed) return;
          try {
            detach = start(container, libraries);
          } catch {
            reportGoogleMapsFailure();
          }
        },
        () => undefined,
      );
      return () => {
        disposed = true;
        detach?.();
      };

      function start(element: HTMLDivElement, libraries: GoogleLibraries): () => void {
        const { initial: first, campuses: around, stations: metro } = startRef.current;
        const size = { width: element.clientWidth, height: element.clientHeight };
        const view = viewForBounds(first, size, evenPadding(FIT_PADDING), {
          minZoom: MIN_ZOOM,
          maxZoom: MAX_ZOOM,
        });
        const map = new libraries.maps.Map(element, {
          ...baseOptions(libraries, config, "fills-screen"),
          // As MapLibre's: fitted to the whole map, then centred in the part the list leaves.
          center: centerBeside(view.center, view.zoom, insetRef.current),
          zoom: view.zoom,
          minZoom: MIN_ZOOM,
          maxZoom: MAX_ZOOM,
        });
        const vectorNow = () => isVector(map);
        const camera = new Camera(map, vectorNow);
        const person = new PersonWatch(element, () => {
          camera.stop();
        });
        const drawn: Drawn = {
          map,
          libraries,
          camera,
          person,
          markers: new Map(),
          rings: [],
          label: null,
        };
        drawnRef.current = drawn;
        const dots = [
          ...around.map((place) =>
            dot(libraries, map, place, {
              width: "8px",
              height: "8px",
              background: brand.colors.primary,
              border: "1.5px solid #ffffff",
            }),
          ),
          ...metro.map((place) =>
            dot(libraries, map, place, {
              width: "10px",
              height: "10px",
              background: "#ffffff",
              border: `3px solid ${STATION_COLOUR}`,
            }),
          ),
        ];
        showCampus(drawn, campusRef.current);

        let named = false;
        const listeners = [
          map.addListener("dragstart", () => {
            person.mark();
          }),
          map.addListener("bounds_changed", () => {
            person.onMove();
          }),
          map.addListener("renderingtype_changed", () => {
            setVector(vectorNow());
          }),
          map.addListener("idle", () => {
            // A glide's frames each end in idle; only the last counts as coming to rest.
            if (camera.moving) return;
            const bounds = map.getBounds();
            const zoom = map.getZoom();
            if (bounds === undefined || zoom === undefined) return;
            if (!named) {
              named = true;
              nameMap(element, callbacksRef.current.text.map);
            }
            callbacksRef.current.onBoundsChange(
              boundsOf(bounds),
              fromGoogleZoom(zoom),
              person.take(),
            );
            drawMarkers();
            setLimits({ atMin: zoom <= MIN_ZOOM + 0.01, atMax: zoom >= MAX_ZOOM - 0.01 });
            setTilted((map.getTilt() ?? 0) > 1);
          }),
        ];
        setVector(vectorNow());
        goToTarget(drawn);

        return () => {
          camera.stop();
          person.dispose();
          for (const listener of listeners) listener.remove();
          for (const { marker } of drawn.markers.values()) marker.map = null;
          for (const marker of dots) marker.map = null;
          showCampus(drawn, undefined);
          drawnRef.current = null;
        };
      }
    },
    [config, drawMarkers, showCampus, goToTarget],
  );

  // New pins: cluster them afresh, and draw what the view holds now.
  useEffect(() => {
    clustersRef.current = new PinClusters(pins);
    drawMarkers();
  }, [pins, drawMarkers]);

  // The campus searched near: its rings and its name.
  useEffect(() => {
    const campus = campuses.find((place) => place.slug === chosenCampus);
    campusRef.current = campus;
    const drawn = drawnRef.current;
    if (drawn !== null) showCampus(drawn, campus);
  }, [campuses, chosenCampus, text.campus, showCampus]);

  // A new place to show: fly there, as the page's move rather than the person's. One that comes
  // while Google's script is still loading waits for the map.
  useEffect(() => {
    targetRef.current = target;
    const drawn = drawnRef.current;
    if (drawn !== null) goToTarget(drawn);
  }, [target, goToTarget]);

  useEffect(() => {
    highlightRef.current = { selectedId, hoveredId };
    const drawn = drawnRef.current;
    if (drawn !== null) highlight(drawn.markers, highlightRef.current);
  }, [selectedId, hoveredId]);

  // What the floating list covers stays out of the map's centre, as MapLibre's padding keeps it:
  // when it widens or narrows, the view shifts by half the change.
  useEffect(() => {
    const change = insetLeft - insetRef.current;
    insetRef.current = insetLeft;
    const map = drawnRef.current?.map;
    const center = map?.getCenter();
    const zoom = map?.getZoom();
    if (change === 0 || map === undefined || center === undefined || zoom === undefined) return;
    map.moveCamera({
      center: centerBeside({ lat: center.lat(), lng: center.lng() }, zoom, change),
    });
  }, [insetLeft]);

  function zoomBy(step: 1 | -1) {
    const drawn = drawnRef.current;
    const zoom = drawn?.map.getZoom();
    if (drawn === null || zoom === undefined) return;
    drawn.person.mark();
    drawn.camera.ease({ zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom + step)) }, STEP_MS);
  }

  function toggleTilt() {
    const next = !tilted;
    setTilted(next);
    drawnRef.current?.camera.ease({ tilt: next ? TILT : 0, heading: next ? HEADING : 0 }, TILT_MS);
  }

  return (
    <div className="search-map relative h-full min-h-72 w-full">
      <div ref={attach} className="h-full w-full overflow-hidden" />
      <ZoomButtons
        onZoom={zoomBy}
        atMin={limits.atMin}
        atMax={limits.atMax}
        text={text}
        className="top-2.5 lg:top-[6.125rem]"
      />
      {/* Tilt needs the vector map; where Google falls back to raster, the map stays flat. */}
      {vector ? <TiltButton tilted={tilted} onToggle={toggleTilt} text={text} /> : null}
      {/* Campuses and stations come from OpenStreetMap (ADR 0020), credited beside Google's own. */}
      <a
        href={OSM_COPYRIGHT}
        target="_blank"
        rel="noreferrer"
        className="absolute right-1 bottom-5 z-10 rounded-sm bg-background/85 px-1 text-[10px] leading-4 text-foreground underline"
      >
        {text.osmCredit}
      </a>
    </div>
  );
}

/** What a pin's or cluster's marker says, which pin or cluster it is, and where. */
function describe(
  { marker, face }: { marker: AdvancedMarker; face: HTMLElement },
  item: MapItem,
  { shortPrice, text }: Pick<Callbacks, "shortPrice" | "text">,
): void {
  marker.position = { lat: item.lat, lng: item.lng };
  marker.dataset.lat = String(item.lat);
  marker.dataset.lng = String(item.lng);
  const { shown, name } = itemWords(item, text, shortPrice);
  face.textContent = shown;
  marker.setAttribute("aria-label", name);
  if (item.kind === "cluster") {
    face.className = clusterFace;
    marker.dataset.clusterId = String(item.clusterId);
    return;
  }
  face.className = pinFace;
  marker.dataset.pinId = item.id;
  marker.dataset.verified = String(item.verified);
}

function highlight(
  markers: Drawn["markers"],
  { selectedId, hoveredId }: { selectedId: string | null; hoveredId: string | null },
): void {
  for (const { marker } of markers.values()) {
    const id = marker.dataset.pinId;
    if (id === undefined) continue;
    const active = id === selectedId || id === hoveredId;
    marker.dataset.state = active ? "active" : "idle";
    marker.setAttribute("aria-pressed", String(id === selectedId));
    // Above its neighbours while it's the one being looked at.
    marker.zIndex = active ? 2 : 1;
  }
}
