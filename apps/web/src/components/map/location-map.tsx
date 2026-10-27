"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import { publicEnv } from "@/config/env";

import type { LocationMapProps } from "./map-provider";

const placeholder = () => (
  <div className="h-64 w-full animate-pulse rounded-md bg-muted motion-reduce:animate-none" />
);

const MapLibreLocationMap = dynamic(() => import("./maplibre/location-map"), {
  ssr: false,
  loading: placeholder,
});

/**
 * A PG's area on a small map (ADR 0030), from whichever map this site is set up with. Its code
 * loads only once the map scrolls near the screen, so it costs the page nothing until then; with
 * no map tiles, there's no map (the page says where the PG is in words).
 */
export function LocationMap(props: LocationMapProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [near, setNear] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (element === null) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);

  const tiles = publicEnv.mapTiles;
  if (tiles === undefined) return null;
  return (
    <div ref={ref}>{near ? <MapLibreLocationMap {...props} tiles={tiles} /> : placeholder()}</div>
  );
}
