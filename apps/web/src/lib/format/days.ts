/**
 * Days as the site handles them: "YYYY-MM-DD" strings for days in India, read and counted on
 * the calendar without a time zone in between.
 */

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
