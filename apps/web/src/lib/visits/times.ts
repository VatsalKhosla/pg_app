/**
 * The times a student may offer for a visit, as the API allows them (step 3.7; the API's
 * app/modules/visits/domain/visits.py): on the hour or half past, from 9 am to 7 pm in India,
 * from three hours ahead to two weeks ahead. The API has the last word; these are the choices
 * the form offers.
 */

export const DAYS_AHEAD = 14;
const FIRST_MINUTE = 9 * 60;
const LAST_MINUTE = 19 * 60;
const STEP_MINUTES = 30;
const INDIA_OFFSET = "+05:30";

/** "YYYY-MM-DD" in India for a moment. */
export function indiaDate(moment: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(moment);
}

/** Today in India and the days after it, as "YYYY-MM-DD". */
export function visitDays(now: Date): string[] {
  const [year, month, day] = indiaDate(now).split("-").map(Number) as [number, number, number];
  return Array.from({ length: DAYS_AHEAD }, (_, offset) => {
    const date = new Date(Date.UTC(year, month - 1, day + offset));
    return date.toISOString().slice(0, 10);
  });
}

/** "09:00" to "19:00", every half hour. */
export function visitTimes(): string[] {
  const times: string[] = [];
  for (let minute = FIRST_MINUTE; minute <= LAST_MINUTE; minute += STEP_MINUTES) {
    times.push(
      `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`,
    );
  }
  return times;
}

/** A day and a time in India as the instant the API takes. */
export function visitStart(day: string, time: string): string {
  return new Date(`${day}T${time}:00${INDIA_OFFSET}`).toISOString();
}
