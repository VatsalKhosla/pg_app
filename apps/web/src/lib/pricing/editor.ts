import { bpsToPercentInput } from "@/lib/forms/units";

/**
 * The pricing editor's helpers (step 4.6, ADR 0041). None of them works out a price: rates are
 * shown as the API keeps them, days are counted on the calendar, and the API's rents are only
 * placed on a chart's scale.
 */

/** The API's limits (apps/api/src/app/modules/pricing): move-ins a year ahead, rule labels. */
export const PREVIEW_DAYS = 366;
export const LABEL_MAX = 40;
export const TIERS_MAX = 5;
export const MAX_STAY_MONTHS = 36;
export { DEFAULT_STAY } from "./calendar";

const MINUS = "−";

/** A rule's change as people read it: 1500 is "+15%", −250 is "−2.5%" (a real minus sign). */
export function bpsText(bps: number): string {
  return `${bps < 0 ? MINUS : "+"}${bpsToPercentInput(Math.abs(bps))}%`;
}

/** Basis points of beds taken as a plain percentage: 7000 is "70%". */
export function shareText(bps: number): string {
  return `${bpsToPercentInput(bps)}%`;
}

const MONTH_DAY = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const DAY = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const SHORT_DAY = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

function parts(day: string): [number, number, number] {
  const [year = 0, month = 1, date = 1] = day.split("-").map(Number);
  return [year, month, date];
}

/** A season's "MM-DD" as people read it: "08-01" is "1 Aug" (in a leap year, so 29 Feb is). */
export function monthDayText(monthDay: string): string {
  const [month = 1, day = 1] = monthDay.split("-").map(Number);
  return MONTH_DAY.format(Date.UTC(2000, month - 1, day));
}

/** A "YYYY-MM-DD" day as people read it: "4 Aug 2027", or "4 Aug" when `short`. */
export function dayText(day: string, { short = false }: { short?: boolean } = {}): string {
  const [year, month, date] = parts(day);
  return (short ? SHORT_DAY : DAY).format(Date.UTC(year, month - 1, date));
}

/** "YYYY-MM-DD" plus whole days, on the calendar. */
export function addDays(day: string, days: number): string {
  const [year, month, date] = parts(day);
  return new Date(Date.UTC(year, month - 1, date + days)).toISOString().slice(0, 10);
}

/** Whether a month has the day, in a leap year (a season may start on 29 Feb). */
export function isMonthDay(month: number, day: number): boolean {
  if (!Number.isInteger(month) || !Number.isInteger(day) || month < 1 || month > 12) return false;
  return day >= 1 && day <= new Date(Date.UTC(2000, month, 0)).getUTCDate();
}

/** Round steps for a rent axis, in paise: ₹500, ₹1,000, ₹2,000, ₹2,500, ₹5,000 and so on. */
const STEPS = [500, 1_000, 2_000, 2_500, 5_000, 10_000, 20_000, 25_000, 50_000].map(
  (rupees) => rupees * 100,
);

export interface Scale {
  min: number;
  max: number;
  ticks: number[];
}

/**
 * A rent axis that shows every value given (the week's rents, the listed rent, the band's ends)
 * with at most `most` round steps, and at least one: a flat price sits mid-chart.
 */
export function rentScale(values: readonly number[], most = 5): Scale {
  const low = Math.min(...values);
  const high = Math.max(...values);
  for (const step of STEPS) {
    let min = Math.floor(low / step) * step;
    let max = Math.ceil(high / step) * step;
    if (min === max) {
      min -= step;
      max += step;
    }
    if ((max - min) / step <= most) {
      const ticks = Array.from(
        { length: (max - min) / step + 1 },
        (_, index) => min + index * step,
      );
      return { min: Math.max(min, 0), max, ticks: ticks.filter((tick) => tick >= 0) };
    }
  }
  const step = STEPS.at(-1) ?? 1;
  return {
    min: Math.floor(low / step) * step,
    max: Math.ceil(high / step) * step,
    ticks: [Math.floor(low / step) * step, Math.ceil(high / step) * step],
  };
}
