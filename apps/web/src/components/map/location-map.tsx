"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import { publicEnv } from "@/config/env";

import { hasAnyMap, useMapChoice } from "./choice";
import type { LocationMapProps } from "./map-provider";

const placeholder = () => (
  <div className="h-64 w-full animate-pulse rounded-md bg-muted motion-reduce:animate-none" />
);

const MapLibreLocationMap = dynamic(() => import("./maplibre/location-map"), {
  ssr: false,
  loading: placeholder,
});
const GoogleLocationMap = dynamic(() => import("./google/location-map"), {
  ssr: false,
  loading: placeholder,
});

/**
 * A PG's area on a small map (ADR 0030), from whichever map this site is set up with (ADR 0069).
 * Its code loads only once the map scrolls near the screen, so it costs the page nothing until
 * then; with no map at all, there's none (the page says where the PG is in words).
 */
export function LocationMap(props: LocationMapProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [near, setNear] = useState(false);
  const choice = useMapChoice();

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

  if (!hasAnyMap) return null;
  return <div ref={ref}>{near ? <Chosen choice={choice} {...props} /> : placeholder()}</div>;
}

function Chosen({
  choice,
  ...props
}: LocationMapProps & { choice: ReturnType<typeof useMapChoice> }) {
  const { googleMaps, mapTiles } = publicEnv;
  if (choice === "google" && googleMaps !== undefined) {
    return <GoogleLocationMap {...props} config={googleMaps} />;
  }
  if (choice === "maplibre" && mapTiles !== undefined) {
    return <MapLibreLocationMap {...props} tiles={mapTiles} />;
  }
  return (
    <p className="rounded-2xl border border-dashed bg-surface p-5 text-sm text-muted-foreground">
      {props.text.failed}
    </p>
  );
}
