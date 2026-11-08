"use client";

import type { Route } from "next";
import Link from "next/link";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { formatINR } from "@/lib/money";
import { type MapPin, mapPins } from "@/lib/search/client";
import { serializeSearch } from "@/lib/search/params";

export interface BudgetExplorerText {
  budget: string;
  one: string;
  other: string;
  none: string;
  more: string;
  cta: string;
  monthly: string;
  caption: string;
  mapLabel: string;
}

/** Delhi NCR, as the map's pins are asked for: west, south, east, north. */
const NCR = "76.8,28.3,77.6,28.95";
/** The whole region at once: a zoom that asks for pins, not a street's worth of detail. */
const NCR_ZOOM = 11;
const STEP_PAISE = 50_000;
const WIDTH = 800;
const HEIGHT = 520;
const MARGIN = 56;

function roundDown(paise: number) {
  return Math.floor(paise / STEP_PAISE) * STEP_PAISE;
}

function roundUp(paise: number) {
  return Math.ceil(paise / STEP_PAISE) * STEP_PAISE;
}

/** Fits the pins to the drawing, keeping north up and the map's proportions. */
function project(pins: readonly MapPin[]) {
  const lats = pins.map((pin) => pin.lat);
  const lngs = pins.map((pin) => pin.lng);
  const middle = (Math.min(...lats) + Math.max(...lats)) / 2;
  const squeeze = Math.cos((middle * Math.PI) / 180);
  const west = Math.min(...lngs);
  const north = Math.max(...lats);
  const spanX = Math.max((Math.max(...lngs) - west) * squeeze, 0.01);
  const spanY = Math.max(north - Math.min(...lats), 0.01);
  const scale = Math.min((WIDTH - 2 * MARGIN) / spanX, (HEIGHT - 2 * MARGIN) / spanY);
  const offsetX = (WIDTH - spanX * scale) / 2;
  const offsetY = (HEIGHT - spanY * scale) / 2;
  return (pin: MapPin) => ({
    x: offsetX + (pin.lng - west) * squeeze * scale,
    y: offsetY + (north - pin.lat) * scale,
  });
}

/**
 * Drag a budget and the city's real PGs light up on a night map: each dot is a listing from the
 * map's own pins, lit when its lowest rent is within the budget. It opens search with the same
 * filter. If the pins can't be had, the page keeps what the server drew.
 */
export function BudgetExplorer({
  text,
  children,
}: {
  text: BudgetExplorerText;
  children: ReactNode;
}) {
  const [pins, setPins] = useState<readonly MapPin[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [budget, setBudget] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    mapPins({ bbox: NCR, zoom: NCR_ZOOM }, controller.signal)
      .then((found) => {
        setPins(found.pins);
        setTruncated(found.truncated);
      })
      .catch(() => undefined);
    return () => {
      controller.abort();
    };
  }, []);

  const bounds = useMemo(() => {
    if (pins.length === 0) return null;
    const rents = pins.map((pin) => pin.minRentPaise).sort((a, b) => a - b);
    const lowest = Math.min(...rents);
    return {
      min: roundDown(lowest),
      max: roundUp(Math.max(...rents)),
      start: roundUp(rents[Math.floor(rents.length / 2)] ?? lowest),
    };
  }, [pins]);
  const toPoint = useMemo(() => (pins.length === 0 ? null : project(pins)), [pins]);

  if (bounds === null || toPoint === null || bounds.min === bounds.max) return <>{children}</>;

  const value = budget ?? bounds.start;
  const lit = pins.filter((pin) => pin.minRentPaise <= value).length;
  const fill = ((value - bounds.min) / (bounds.max - bounds.min)) * 100;
  const countText = lit === 0 ? text.none : lit === 1 ? text.one : text.other;
  const count = countText
    .replace("{count}", truncated ? String(lit) + "+" : String(lit))
    .replace("{budget}", formatINR(value));
  const href = `/search${serializeSearch({ budget_max_paise: value })}` as Route;

  return (
    <div className="grid gap-10 lg:grid-cols-[1fr_1.25fr] lg:items-center lg:gap-16">
      <div className="min-w-0">
        <p className="text-sm font-medium text-night-muted">{text.budget}</p>
        <p className="mt-1 font-display text-display font-medium text-night-accent tabular-nums">
          {formatINR(value)}
          <span className="ml-2 font-sans text-base font-normal text-night-muted">
            {text.monthly}
          </span>
        </p>
        <input
          type="range"
          min={bounds.min}
          max={bounds.max}
          step={STEP_PAISE}
          value={value}
          onChange={(event) => {
            setBudget(Number(event.target.value));
          }}
          aria-label={text.budget}
          aria-valuetext={formatINR(value)}
          className="range-sun mt-6 w-full"
          style={{ "--fill": String(fill) + "%" }}
        />
        <p aria-live="polite" className="mt-6 min-h-14 text-xl leading-snug text-night-foreground">
          {count}
          {truncated ? ` ${text.more}` : ""}
        </p>
        <Link
          href={href}
          className={buttonVariants({
            variant: "sun",
            size: "lg",
            shape: "pill",
            className: "mt-4",
          })}
        >
          {text.cta}
        </Link>
      </div>

      <figure className="m-0 min-w-0">
        <svg
          viewBox={String.raw`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={text.mapLabel}
          className="block h-auto w-full"
        >
          <defs>
            <pattern id="night-grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <circle cx="1.5" cy="1.5" r="1.1" fill="var(--night-foreground)" opacity="0.14" />
            </pattern>
          </defs>
          <rect width={WIDTH} height={HEIGHT} fill="url(#night-grid)" />
          {pins.map((pin) => {
            const { x, y } = toPoint(pin);
            const on = pin.minRentPaise <= value;
            return (
              <g key={pin.id} className="budget-pin" data-on={on}>
                <circle cx={x} cy={y} r="24" className="budget-pin-glow" />
                <circle cx={x} cy={y} r="7" className="budget-pin-dot" />
              </g>
            );
          })}
        </svg>
        <figcaption className="mt-2 text-sm text-night-muted">{text.caption}</figcaption>
      </figure>
    </div>
  );
}
