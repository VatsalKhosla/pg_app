"use client";

import { useCallback, useRef, useState } from "react";

import { brand } from "@/config/brand";
import type { GoogleMapsConfig } from "@/config/env";

import { reportGoogleMapsFailure } from "../choice";
import type { LocationMapProps } from "../map-provider";
import { Camera } from "./camera";
import { toGoogleZoom } from "./geometry";
import { baseOptions, isVector, loadGoogleMaps, nameMap } from "./loader";
import { ZoomButtons } from "./zoom-buttons";

/** Close enough to see the streets around, far enough to see the whole circle (MapLibre's 15). */
const AREA_ZOOM = toGoogleZoom(15);
const MIN_ZOOM = toGoogleZoom(9);
const MAX_ZOOM = toGoogleZoom(18);
const STEP_MS = 500;

/** The Google adapter's area map (ADR 0069): Google's map and a soft circle, nothing to drag. */
export default function GoogleLocationMap({
  config,
  center,
  radiusM,
  text,
}: LocationMapProps & { config: GoogleMapsConfig }) {
  const initialRef = useRef({ center, radiusM, text });
  const cameraRef = useRef<{ camera: Camera; map: google.maps.Map } | null>(null);
  const [limits, setLimits] = useState({ atMin: false, atMax: false });

  const attach = useCallback(
    (container: HTMLDivElement | null) => {
      if (container === null) return;
      let disposed = false;
      let detach: (() => void) | null = null;
      loadGoogleMaps(config).then(
        (libraries) => {
          if (disposed) return;
          try {
            const { center: middle, radiusM: radius, text: words } = initialRef.current;
            const map = new libraries.maps.Map(container, {
              ...baseOptions(libraries, config, "in-page"),
              center: middle,
              zoom: AREA_ZOOM,
              minZoom: MIN_ZOOM,
              maxZoom: MAX_ZOOM,
            });
            const area = new libraries.maps.Circle({
              map,
              center: middle,
              radius,
              clickable: false,
              fillColor: brand.colors.primary,
              fillOpacity: 0.18,
              strokeColor: brand.colors.primary,
              strokeOpacity: 1,
              strokeWeight: 2,
            });
            const camera = new Camera(map, () => isVector(map));
            cameraRef.current = { camera, map };
            let named = false;
            const idle = map.addListener("idle", () => {
              if (camera.moving) return;
              if (!named) {
                named = true;
                nameMap(container, words.map);
              }
              const zoom = map.getZoom() ?? AREA_ZOOM;
              setLimits({ atMin: zoom <= MIN_ZOOM + 0.01, atMax: zoom >= MAX_ZOOM - 0.01 });
            });
            const stop = () => {
              camera.stop();
            };
            container.addEventListener("pointerdown", stop, { capture: true, passive: true });
            container.addEventListener("wheel", stop, { capture: true, passive: true });
            detach = () => {
              camera.stop();
              idle.remove();
              area.setMap(null);
              container.removeEventListener("pointerdown", stop, { capture: true });
              container.removeEventListener("wheel", stop, { capture: true });
              cameraRef.current = null;
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

  function zoomBy(step: 1 | -1) {
    const current = cameraRef.current;
    const zoom = current?.map.getZoom();
    if (current === null || zoom === undefined) return;
    current.camera.ease({ zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom + step)) }, STEP_MS);
  }

  return (
    <div className="relative h-64 w-full overflow-hidden rounded-2xl border shadow-xs">
      <div ref={attach} className="h-full w-full" />
      <ZoomButtons onZoom={zoomBy} atMin={limits.atMin} atMax={limits.atMax} text={text} />
    </div>
  );
}
