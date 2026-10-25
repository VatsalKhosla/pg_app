/**
 * Money is integer paise everywhere (CLAUDE.md rule 12). The browser never works out a price: it
 * shows what the API sends, and turns the rupees staff type into paise without floating point.
 */

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
const wholeInr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

/** ₹12,000 for 1200000 paise; ₹12,000.50 when there are paise. */
export function formatINR(paise: number): string {
  return paise % 100 === 0 ? wholeInr.format(paise / 100) : inr.format(paise / 100);
}

/** The rupees on a form, for its input. */
export function paiseToRupeesInput(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "";
  const rupees = Math.trunc(paise / 100);
  const rest = paise % 100;
  return rest === 0 ? String(rupees) : `${String(rupees)}.${String(rest).padStart(2, "0")}`;
}

const AMOUNT = /^(\d{1,9})(?:\.(\d{1,2}))?$/;

/** "12,000" or "12000.5" as paise (1200000, 1200050); null for anything else. */
export function rupeesToPaise(input: string): number | null {
  const match = AMOUNT.exec(input.replaceAll(",", "").replaceAll("₹", "").trim());
  if (match === null) return null;
  const rupees = Number(match[1]);
  const paise = Number((match[2] ?? "").padEnd(2, "0"));
  return rupees * 100 + paise;
}
