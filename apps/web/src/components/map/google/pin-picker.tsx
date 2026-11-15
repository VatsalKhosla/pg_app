"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { GoogleMapsConfig } from "@/config/env";

import { reportGoogleMapsFailure } from "../choice";
import { type LatLng, NCR_BOUNDS, type PinPickerProps, roundCoordinate } from "../map-provider";
import { Camera } from "./camera";
import { evenPadding, nudge, toGoogleZoom, viewForBounds } from "./geometry";
import { baseOptions, isVector, loadGoogleMaps, nameMap } from "./loader";
import { ZoomButtons } from "./zoom-buttons";

/** Close enough to tell which building the pin is on (MapLibre's 17 and 14). */
const PIN_ZOOM = toGoogleZoom(17);
const LOCALITY_ZOOM = toGoogleZoom(14);
const MIN_ZOOM = toGoogleZoom(8);
const MAX_ZOOM = 22;
const STEP_MS = 500;
// The arrow keys move the pin a pixel at a time, or ten with Shift, as MapLibre's pin moves.
const ARROWS: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
};

function toLatLng(point: LatLng): LatLng {
  return { lat: roundCoordinate(point.lat), lng: roundCoordinate(point.lng) };
}

function samePlace(a: LatLng, b: LatLng): boolean {
  return (
    roundCoordinate(a.lat) === roundCoordinate(b.lat) &&
    roundCoordinate(a.lng) === roundCoordinate(b.lng)
  );
}

/** Where the pin is, whichever form Google holds it in. */
function positionOf(pin: google.maps.marker.AdvancedMarkerElement): LatLng | null {
  const position = pin.position;
  if (position === null || position === undefined) return null;
  return typeof position.lat === "function"
    ? { lat: (position as google.maps.LatLng).lat(), lng: (position as google.maps.LatLng).lng() }
    : (position as google.maps.LatLngLiteral);
}

interface Picker {
  map: google.maps.Map;
  pin: google.maps.marker.AdvancedMarkerElement;
  camera: Camera;
}

/**
 * The Google adapter's pin picker (ADR 0023, 0069): Google's map and its own draggable pin. Ops
 * drag the pin, click or tap where it goes, or move it with the arrow keys once it has focus.
 */
export default function GooglePinPicker({
  config,
  value,
  onChange,
  center,
  text,
}: PinPickerProps & { config: GoogleMapsConfig }) {
  const pickerRef = useRef<Picker | null>(null);
  const onChangeRef = useRef(onChange);
  // Where the map starts: the pin or the centre as they are once its script has loaded.
  const latestRef = useRef({ value, center, text });
  const [limits, setLimits] = useState({ atMin: false, atMax: false });

  useEffect(() => {
    onChangeRef.current = onChange;
    latestRef.current = { value, center, text };
  }, [onChange, value, center, text]);

  const attach = useCallback(
    (container: HTMLDivElement | null) => {
      if (container === null) return;
      let disposed = false;
      let detach: (() => void) | null = null;
      loadGoogleMaps(config).then(
        (libraries) => {
          if (disposed) return;
          try {
            const { value: start, center: around, text: words } = latestRef.current;
            const size = { width: container.clientWidth, height: container.clientHeight };
            const view =
              start !== null
                ? { center: start, zoom: PIN_ZOOM }
                : around !== undefined
                  ? { center: around, zoom: LOCALITY_ZOOM }
                  : viewForBounds(NCR_BOUNDS, size, evenPadding(0), {
                      minZoom: MIN_ZOOM,
                      maxZoom: MAX_ZOOM,
                    });
            const map = new libraries.maps.Map(container, {
              ...baseOptions(libraries, config, "in-page"),
              ...view,
              minZoom: MIN_ZOOM,
              maxZoom: MAX_ZOOM,
            });
            const pin = new libraries.marker.AdvancedMarkerElement({
              gmpDraggable: true,
              ...(start === null ? {} : { position: start, map }),
            });
            pin.setAttribute("aria-label", words.pin);
            pin.setAttribute("role", "button");
            pin.tabIndex = 0;
            const camera = new Camera(map, () => isVector(map));
            pickerRef.current = { map, pin, camera };

            const commit = () => {
              const at = positionOf(pin);
              if (at !== null) onChangeRef.current(toLatLng(at));
            };
            let keyed = false;
            const onKeyDown = (event: KeyboardEvent) => {
              const delta = ARROWS[event.key];
              if (delta === undefined || event.altKey || event.ctrlKey || event.metaKey) return;
              const at = positionOf(pin);
              const zoom = map.getZoom();
              if (at === null || zoom === undefined) return;
              // The pin moves, not the map behind it.
              event.preventDefault();
              event.stopPropagation();
              const step = event.shiftKey ? 10 : 1;
              pin.position = nudge(at, zoom, delta[0] * step, delta[1] * step);
              keyed = true;
            };
            const onKeyUp = (event: KeyboardEvent) => {
              if (ARROWS[event.key] === undefined || !keyed) return;
              keyed = false;
              commit();
            };
            const onBlur = () => {
              if (!keyed) return;
              keyed = false;
              commit();
            };
            pin.addEventListener("keydown", onKeyDown, { capture: true });
            pin.addEventListener("keyup", onKeyUp);
            pin.addEventListener("blur", onBlur);
            pin.addEventListener("gmp-dragend", commit);
            const listeners = [
              map.addListener("click", (event: google.maps.MapMouseEvent) => {
                if (event.latLng === null) return;
                pin.position = event.latLng;
                pin.map ??= map;
                onChangeRef.current(toLatLng({ lat: event.latLng.lat(), lng: event.latLng.lng() }));
              }),
              map.addListener("idle", () => {
                if (camera.moving) return;
                nameMap(container, words.map);
                const zoom = map.getZoom() ?? MIN_ZOOM;
                setLimits({ atMin: zoom <= MIN_ZOOM + 0.01, atMax: zoom >= MAX_ZOOM - 0.01 });
              }),
            ];
            const stop = () => {
              camera.stop();
            };
            container.addEventListener("pointerdown", stop, { capture: true, passive: true });
            container.addEventListener("wheel", stop, { capture: true, passive: true });
            detach = () => {
              camera.stop();
              for (const listener of listeners) listener.remove();
              pin.map = null;
              container.removeEventListener("pointerdown", stop, { capture: true });
              container.removeEventListener("wheel", stop, { capture: true });
              pickerRef.current = null;
            };
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
    },
    [config],
  );

  // A pin set outside the map (GPS, typed coordinates): move the pin there and look at it. With
  // no pin yet, look at the centre instead (a locality just chosen).
  const centerLat = center?.lat;
  const centerLng = center?.lng;
  useEffect(() => {
    const picker = pickerRef.current;
    if (picker === null) return;
    const { map, pin, camera } = picker;
    if (value === null) {
      pin.map = null;
      if (centerLat !== undefined && centerLng !== undefined) {
        camera.ease({ center: { lat: centerLat, lng: centerLng }, zoom: LOCALITY_ZOOM }, STEP_MS);
      }
      return;
    }
    const onMap = pin.map !== null && pin.map !== undefined;
    const at = positionOf(pin);
    if (onMap && at !== null && samePlace(toLatLng(at), value)) return;
    pin.position = value;
    if (!onMap) pin.map = map;
    camera.ease({ center: value, zoom: Math.max(map.getZoom() ?? 0, PIN_ZOOM) }, STEP_MS);
  }, [value, centerLat, centerLng]);

  function zoomBy(step: 1 | -1) {
    const picker = pickerRef.current;
    const zoom = picker?.map.getZoom();
    if (picker === null || zoom === undefined) return;
    picker.camera.ease({ zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom + step)) }, STEP_MS);
  }

  return (
    <div className="relative h-72 w-full overflow-hidden rounded-2xl border shadow-xs sm:h-96">
      <div ref={attach} className="h-full w-full" />
      <ZoomButtons onZoom={zoomBy} atMin={limits.atMin} atMax={limits.atMax} text={text} />
    </div>
  );
}
