/**
 * Rates on the admin forms (ADR 0036): the API keeps them in basis points (30% is 3000), and
 * admins type percentages. Converted without floating point, as money is.
 */

const PERCENT = /^(\d{1,3})(?:\.(\d{1,2}))?$/u;

/** "30" or "18.5" as basis points (3000, 1850); null for anything else. */
export function percentToBps(input: string): number | null {
  const match = PERCENT.exec(input.replaceAll("%", "").trim());
  if (match === null) return null;
  const whole = Number(match[1]);
  const hundredths = Number((match[2] ?? "").padEnd(2, "0"));
  return whole * 100 + hundredths;
}

/** Basis points as a form's percentage: 3000 is "30", 1850 is "18.5", 25 is "0.25". */
export function bpsToPercentInput(bps: number): string {
  const whole = Math.trunc(bps / 100);
  const rest = bps % 100;
  if (rest === 0) return String(whole);
  return `${String(whole)}.${String(rest).padStart(2, "0").replace(/0$/u, "")}`;
}

/** A whole number someone typed, or null. */
export function wholeNumber(input: string): number | null {
  const text = input.trim();
  return /^\d{1,9}$/u.test(text) ? Number(text) : null;
}
