import type { ReactNode } from "react";

const SIZE = 120;
const RADIUS = 50;
const STROKE = 13;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * A part of a whole as a ring (dataviz: a two-part whole, so the filled arc and its track are the
 * only marks): ``value`` out of ``total``, with whatever ``children`` say in its middle. The ring
 * itself is decoration; the words in the middle and beside it carry the numbers, for everyone.
 * The arc draws in once, except for people who ask for less motion.
 */
export function RingMeter({
  value,
  total,
  children,
}: {
  value: number;
  total: number;
  children: ReactNode;
}) {
  const share = total > 0 ? Math.min(Math.max(value / total, 0), 1) : 0;
  const length = share * CIRCUMFERENCE;
  const centre = SIZE / 2;
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[15rem]">
      <svg viewBox={`0 0 ${String(SIZE)} ${String(SIZE)}`} aria-hidden="true" className="size-full">
        <circle
          cx={centre}
          cy={centre}
          r={RADIUS}
          fill="none"
          strokeWidth={STROKE}
          className="ring-meter-track"
        />
        {length > 0 ? (
          <circle
            cx={centre}
            cy={centre}
            r={RADIUS}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap={share < 1 ? "round" : "butt"}
            strokeDasharray={`${length.toFixed(2)} ${CIRCUMFERENCE.toFixed(2)}`}
            transform={`rotate(-90 ${String(centre)} ${String(centre)})`}
            className="ring-meter-arc"
            style={{ "--arc": length.toFixed(2) }}
          />
        ) : null}
      </svg>
      <div className="absolute inset-0 grid place-items-center p-8 text-center">
        <div>{children}</div>
      </div>
    </div>
  );
}
