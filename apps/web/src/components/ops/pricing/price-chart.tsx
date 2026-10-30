"use client";

import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";

import { formatINR } from "@/lib/money";
import { priceStretches } from "@/lib/pricing/calendar";
import { dayText, rentScale } from "@/lib/pricing/editor";

/**
 * The editor's price chart (step 4.6, ADR 0041): one small chart per room, so each reads against
 * its own listed rent and band. Each is the API's rent for every week's move-in, drawn as steps
 * because a week's price holds for every move-in that week, over the band (a neutral wash) and
 * the listed rent (a hairline). A dot marks a week a limit held back. Pointer and arrow keys read
 * any week; the table under it has every value too. Colours are the chart tokens in
 * globals.css, validated for both themes; the browser places the API's rents and works none out.
 */

type ClampKind =
  "premium_cap" | "discount_cap" | "owner_min" | "owner_max" | "band_min" | "band_max";

export interface ChartWeek {
  moveIn: string;
  monthlyRentPaise: number;
  clamps: readonly ClampKind[];
}

export interface ChartRoom {
  id: string;
  label: string;
  baseRentPaise: number;
  bedsFree: number;
  weeks: readonly ChartWeek[];
  band: { minRentPaise: number; maxRentPaise: number } | null;
}

// The whole chart's height, its x-axis labels included, so its box never scrolls.
const HEIGHT = 224;
const MARGIN = { top: 16, right: 12, bottom: 32, left: 76 };
const FIRST_WIDTH = 480;
// The least room an x-axis date needs, in pixels.
const LABEL_SPACE = 60;
// Past this far right, the readout opens leftwards so it stays inside the chart.
const READOUT_SPACE = 176;

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(FIRST_WIDTH);
  useEffect(() => {
    const element = ref.current;
    if (element === null) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry !== undefined) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);
  return [ref, width];
}

export function PriceCharts({ rooms }: { rooms: readonly ChartRoom[] }) {
  return (
    // Side by side on a wide screen when there are several; one room gets the whole width.
    <div className={rooms.length > 1 ? "grid gap-10 lg:grid-cols-2" : "grid gap-10"}>
      {rooms.map((room) => (
        <RoomChart key={room.id} room={room} />
      ))}
    </div>
  );
}

function RoomChart({ room }: { room: ChartRoom }) {
  const t = useTranslations("Ops.pricing.chart");
  const id = useId();
  const [box, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const weeks = room.weeks;

  const heldBy = (week: ChartWeek) =>
    week.clamps.map((clamp) => t(`heldBy.${clamp}`)).join(", ") || t("noLimit");
  const stretches = priceStretches(weeks);
  const summary = [
    stretches.length === 1 && stretches[0] !== undefined
      ? t("flat", { amount: formatINR(stretches[0].monthlyRentPaise) })
      : stretches
          .map((stretch) =>
            t("stretch", {
              amount: formatINR(stretch.monthlyRentPaise),
              date: dayText(stretch.first, { short: true }),
            }),
          )
          .join(" · "),
    t("bedsFree", { count: room.bedsFree }),
  ].join(" · ");

  return (
    <figure className="min-w-0 space-y-3">
      <figcaption className="space-y-1">
        <h3 id={`${id}-title`} className="font-medium">
          {room.label}
        </h3>
        {weeks.length === 0 ? null : <p className="text-sm text-muted-foreground">{summary}</p>}
      </figcaption>
      {weeks.length === 0 ? (
        <p className="text-sm">{t("unpriced")}</p>
      ) : (
        <>
          <Key
            hasBand={room.band !== null}
            hasHeld={weeks.some((week) => week.clamps.length > 0)}
          />
          <div
            ref={box}
            role="group"
            tabIndex={0}
            aria-label={t("label", { room: room.label })}
            aria-describedby={`${id}-keys`}
            className="relative rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            onKeyDown={(event) => {
              const last = weeks.length - 1;
              const moves: Record<string, () => number | null> = {
                ArrowRight: () => Math.min(last, (active ?? -1) + 1),
                ArrowLeft: () => Math.max(0, (active ?? last + 1) - 1),
                Home: () => 0,
                End: () => last,
                Escape: () => null,
              };
              const move = moves[event.key];
              if (move === undefined) return;
              event.preventDefault();
              setActive(move());
            }}
            onBlur={() => {
              setActive(null);
            }}
          >
            <Plot room={room} width={width} active={active} onActive={setActive} />
            {active === null || weeks[active] === undefined ? null : (
              <Readout
                week={weeks[active]}
                heldBy={heldBy(weeks[active])}
                at={positionOf(active, weeks.length, width)}
                width={width}
              />
            )}
          </div>
          <p id={`${id}-keys`} className="sr-only">
            {t("keys")}
          </p>
          <p aria-live="polite" className="sr-only">
            {active === null || weeks[active] === undefined
              ? ""
              : `${t("week", { date: dayText(weeks[active].moveIn) })}: ${t("perMonth", {
                  amount: formatINR(weeks[active].monthlyRentPaise),
                })}. ${t("limits")}: ${heldBy(weeks[active])}`}
          </p>
          <details className="text-sm">
            <summary className="inline-flex min-h-6 cursor-pointer items-center font-medium text-primary underline underline-offset-4">
              {t("table")}
            </summary>
            <table className="mt-3 w-full text-left">
              <caption className="sr-only">{t("label", { room: room.label })}</caption>
              <thead>
                <tr className="border-b">
                  <th scope="col" className="py-1 pr-4 font-medium">
                    {t("moveIn")}
                  </th>
                  <th scope="col" className="py-1 pr-4 font-medium">
                    {t("rent")}
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    {t("limits")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {weeks.map((week) => (
                  <tr key={week.moveIn} className="border-b last:border-0">
                    <th scope="row" className="py-1 pr-4 font-normal">
                      {dayText(week.moveIn)}
                    </th>
                    <td className="py-1 pr-4 tabular-nums">{formatINR(week.monthlyRentPaise)}</td>
                    <td className="py-1">{heldBy(week)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </figure>
  );
}

/** Where week `index`'s middle is across a chart `width` wide. */
function positionOf(index: number, count: number, width: number): number {
  const plot = Math.max(width - MARGIN.left - MARGIN.right, 1);
  return MARGIN.left + (index + 0.5) * (plot / count);
}

function Key({ hasBand, hasHeld }: { hasBand: boolean; hasHeld: boolean }) {
  const t = useTranslations("Ops.pricing.chart");
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground" aria-hidden="true">
      <li className="flex items-center gap-2">
        <span className="inline-block h-0.5 w-4 rounded-full bg-[var(--chart-series)]" />
        {t("rent")}
      </li>
      {hasBand ? (
        <li className="flex items-center gap-2">
          <span className="inline-block size-3 rounded-sm bg-[var(--chart-band)]" />
          {t("band")}
        </li>
      ) : null}
      <li className="flex items-center gap-2">
        <span className="inline-block h-px w-4 bg-[var(--chart-reference)]" />
        {t("listedKey")}
      </li>
      {hasHeld ? (
        <li className="flex items-center gap-2">
          <span className="inline-block size-2 rounded-full bg-[var(--chart-series)]" />
          {t("held")}
        </li>
      ) : null}
    </ul>
  );
}

function Plot({
  room,
  width,
  active,
  onActive,
}: {
  room: ChartRoom;
  width: number;
  active: number | null;
  onActive: (index: number | null) => void;
}) {
  const t = useTranslations("Ops.pricing.chart");
  const weeks = room.weeks;
  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 1);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const scale = rentScale([
    ...weeks.map((week) => week.monthlyRentPaise),
    room.baseRentPaise,
    ...(room.band === null ? [] : [room.band.minRentPaise, room.band.maxRentPaise]),
  ]);
  const y = (paise: number) =>
    MARGIN.top + plotHeight * (1 - (paise - scale.min) / (scale.max - scale.min));
  const step = plotWidth / weeks.length;
  const x = (index: number) => MARGIN.left + index * step;
  const middle = (index: number) => x(index) + step / 2;
  const every = Math.max(1, Math.ceil(LABEL_SPACE / step));
  const steps = weeks
    .map((week, index) =>
      index === 0
        ? `M ${String(x(0))} ${String(y(week.monthlyRentPaise))}`
        : `H ${String(x(index))} V ${String(y(week.monthlyRentPaise))}`,
    )
    .join(" ");
  const listed = y(room.baseRentPaise);
  const bottom = MARGIN.top + plotHeight;
  const activeWeek = active === null ? undefined : weeks[active];

  return (
    <svg
      width={width}
      height={HEIGHT}
      viewBox={`0 0 ${String(width)} ${String(HEIGHT)}`}
      aria-hidden="true"
      className="block max-w-full touch-pan-y select-none"
      onPointerLeave={() => {
        onActive(null);
      }}
    >
      {room.band === null ? null : (
        <rect
          x={MARGIN.left}
          y={y(room.band.maxRentPaise)}
          width={plotWidth}
          height={Math.max(y(room.band.minRentPaise) - y(room.band.maxRentPaise), 1)}
          className="fill-[var(--chart-band)]"
        />
      )}
      {scale.ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={MARGIN.left}
            x2={MARGIN.left + plotWidth}
            y1={y(tick)}
            y2={y(tick)}
            className="stroke-[var(--chart-grid)]"
            strokeWidth={1}
            shapeRendering="crispEdges"
          />
          <text
            x={MARGIN.left - 8}
            y={y(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            className="fill-muted-foreground text-xs tabular-nums"
          >
            {formatINR(tick)}
          </text>
        </g>
      ))}
      <line
        x1={MARGIN.left}
        x2={MARGIN.left + plotWidth}
        y1={bottom}
        y2={bottom}
        className="stroke-[var(--chart-axis)]"
        strokeWidth={1}
        shapeRendering="crispEdges"
      />
      {weeks.map((week, index) =>
        index % every === 0 ? (
          <text
            key={week.moveIn}
            x={middle(index)}
            y={bottom + 18}
            textAnchor="middle"
            className="fill-muted-foreground text-xs"
          >
            {dayText(week.moveIn, { short: true })}
          </text>
        ) : null,
      )}
      <line
        x1={MARGIN.left}
        x2={MARGIN.left + plotWidth}
        y1={listed}
        y2={listed}
        className="stroke-[var(--chart-reference)]"
        strokeWidth={1}
        shapeRendering="crispEdges"
      />
      <text
        x={MARGIN.left + plotWidth}
        y={listed - 6}
        textAnchor="end"
        className="fill-muted-foreground stroke-background text-xs [paint-order:stroke]"
        strokeWidth={4}
        strokeLinejoin="round"
      >
        {t("listed", { amount: formatINR(room.baseRentPaise) })}
      </text>
      <path
        d={`${steps} H ${String(x(weeks.length))}`}
        fill="none"
        className="stroke-[var(--chart-series)]"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {weeks.map((week, index) =>
        week.clamps.length === 0 ? null : (
          <circle
            key={week.moveIn}
            cx={middle(index)}
            cy={y(week.monthlyRentPaise)}
            r={4}
            className="fill-[var(--chart-series)] stroke-background"
            strokeWidth={2}
          />
        ),
      )}
      {activeWeek === undefined || active === null ? null : (
        <g>
          <line
            x1={middle(active)}
            x2={middle(active)}
            y1={MARGIN.top}
            y2={bottom}
            className="stroke-[var(--chart-axis)]"
            strokeWidth={1}
          />
          <circle
            cx={middle(active)}
            cy={y(activeWeek.monthlyRentPaise)}
            r={5}
            className="fill-[var(--chart-series)] stroke-background"
            strokeWidth={2}
          />
        </g>
      )}
      {weeks.map((week, index) => (
        <rect
          key={week.moveIn}
          x={x(index)}
          y={MARGIN.top}
          width={step}
          height={plotHeight}
          fill="transparent"
          onPointerEnter={() => {
            onActive(index);
          }}
          onPointerDown={() => {
            onActive(index);
          }}
        />
      ))}
    </svg>
  );
}

function Readout({
  week,
  heldBy,
  at,
  width,
}: {
  week: ChartWeek;
  heldBy: string;
  at: number;
  width: number;
}) {
  const t = useTranslations("Ops.pricing.chart");
  const leftwards = at > width - READOUT_SPACE;
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute top-2 z-10 w-max max-w-44 space-y-0.5 rounded-md border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-sm"
      style={leftwards ? { right: width - at + 10 } : { left: at + 10 }}
    >
      <p className="text-sm font-semibold">
        {t("perMonth", { amount: formatINR(week.monthlyRentPaise) })}
      </p>
      <p className="text-muted-foreground">{t("week", { date: dayText(week.moveIn) })}</p>
      {week.clamps.length === 0 ? null : (
        <p className="text-muted-foreground">
          {t("limits")}: {heldBy}
        </p>
      )}
    </div>
  );
}
