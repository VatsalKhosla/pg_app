/** Up to this many week labels under a chart; the rest are in its table and tooltips. */
const LABELS = 6;
const WIDTH = 640;
const HEIGHT = 220;
const LEFT = 48;
const RIGHT = 8;
const TOP = 12;
const BOTTOM = 28;
const RADIUS = 4;

/** The smallest of 1, 2 or 5 times a power of ten at or above ``value``: the chart's top. */
function niceTop(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 5, 10].find((each) => each * power >= value) ?? 10;
  return step * power;
}

/** A bar with its top corners rounded and its base square on the axis. */
function bar(x: number, width: number, top: number, base: number): string {
  const r = Math.min(RADIUS, width / 2, base - top);
  return [
    `M${x.toFixed(1)} ${base.toFixed(1)}`,
    `V${(top + r).toFixed(1)}`,
    `Q${x.toFixed(1)} ${top.toFixed(1)} ${(x + r).toFixed(1)} ${top.toFixed(1)}`,
    `H${(x + width - r).toFixed(1)}`,
    `Q${(x + width).toFixed(1)} ${top.toFixed(1)} ${(x + width).toFixed(1)} ${(top + r).toFixed(1)}`,
    `V${base.toFixed(1)}Z`,
  ].join("");
}

/**
 * One measure, one bar a week, oldest on the left: a single series, so its title names it and it
 * needs no legend. Each bar names its week and value on hover (and to screen readers through the
 * table under it). Drawn on the server, as plain SVG.
 */
export function WeeklyBars({
  id,
  title,
  total,
  weeks,
  values,
  axis,
  value,
  tableLabel,
  weekLabel,
}: {
  id: string;
  title: string;
  /** The period's total, already formatted. */
  total: string;
  /** Each week's label, e.g. "18 Aug". */
  weeks: readonly string[];
  values: readonly number[];
  /** A tick's label (short). */
  axis: (value: number) => string;
  /** A value in full, for its tooltip and the table. */
  value: (value: number) => string;
  tableLabel: string;
  weekLabel: string;
}) {
  const top = niceTop(Math.max(0, ...values));
  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const band = plotWidth / Math.max(values.length, 1);
  const barWidth = Math.max(4, band * 0.62);
  const y = (amount: number) => TOP + plotHeight - (amount / top) * plotHeight;
  const ticks = [0, top / 2, top];
  const every = Math.max(1, Math.ceil(weeks.length / LABELS));

  return (
    <figure className="m-0 flex flex-col gap-3 rounded-[1.75rem] border border-border/70 bg-card p-5 shadow-md sm:p-6">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={`${id}-title`} className="font-sans text-base font-semibold text-foreground">
          {title}
        </h2>
        <span className="text-title-2 font-semibold text-foreground tabular-nums">{total}</span>
      </figcaption>
      <svg
        viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
        className="ops-chart block h-auto w-full"
        role="img"
        aria-labelledby={`${id}-title`}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={LEFT}
              x2={WIDTH - RIGHT}
              y1={y(tick)}
              y2={y(tick)}
              className={tick === 0 ? "ops-chart-axis" : "ops-chart-grid"}
            />
            <text x={LEFT - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="ops-chart-label">
              {axis(tick)}
            </text>
          </g>
        ))}
        {values.map((amount, index) => {
          const x = LEFT + index * band + (band - barWidth) / 2;
          const label = weeks[index] ?? "";
          return (
            <g key={label} className="ops-chart-mark">
              {/* A target the full height of the plot, so a short bar is as easy to hover. */}
              <rect
                x={LEFT + index * band}
                y={TOP}
                width={band}
                height={plotHeight}
                fill="transparent"
              >
                <title>{`${label}: ${value(amount)}`}</title>
              </rect>
              {amount > 0 ? (
                <path d={bar(x, barWidth, y(amount), y(0))} className="ops-chart-bar" />
              ) : null}
              {index % every === 0 || index === values.length - 1 ? (
                <text
                  x={x + barWidth / 2}
                  y={HEIGHT - 8}
                  textAnchor="middle"
                  className="ops-chart-label"
                >
                  {label}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <details className="text-sm">
        <summary className="cursor-pointer font-medium text-muted-foreground">{tableLabel}</summary>
        <table className="mt-2 w-full text-left tabular-nums">
          <thead>
            <tr className="text-muted-foreground">
              <th scope="col" className="py-1 font-medium">
                {weekLabel}
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                {title}
              </th>
            </tr>
          </thead>
          <tbody>
            {values.map((amount, index) => (
              <tr key={weeks[index]} className="border-t border-border/60">
                <td className="py-1">{weeks[index]}</td>
                <td className="py-1 text-right">{value(amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
