/**
 * Prices as a map pin says them: "₹8k–12k" for a range, "₹9k" for one price. Formatting only:
 * the amounts are the API's (CLAUDE.md rule 12), rounded to a short label here.
 */

/** "₹8k", "₹12.5k", or "₹950" under a thousand rupees. */
export function shortRupees(paise: number): string {
  const rupees = Math.round(paise / 100);
  if (rupees < 1_000) return `₹${String(rupees)}`;
  return `₹${String(Math.round(rupees / 100) / 10)}k`;
}

export function priceLabel(minPaise: number, maxPaise: number): string {
  if (shortRupees(minPaise) === shortRupees(maxPaise)) return shortRupees(minPaise);
  return `${shortRupees(minPaise)}–${shortRupees(maxPaise).replace("₹", "")}`;
}
