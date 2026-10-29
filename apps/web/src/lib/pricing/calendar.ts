/**
 * What the PG page may say about prices and beds (step 4.5, ADR 0040), from the API's calendar
 * and nothing else (CLAUDE.md rule 7): a change in price only where the calendar shows one, and
 * scarcity only from real free beds. The browser never works a price out: it groups the weeks
 * the API priced.
 */

export interface Week {
  moveIn: string;
  monthlyRentPaise: number;
}

/** A run of weeks with one price: from its first move-in to its last. */
export interface PriceStretch {
  first: string;
  last: string;
  monthlyRentPaise: number;
}

/** The calendar's weeks, grouped where the price stays the same, in order. */
export function priceStretches(weeks: readonly Week[]): PriceStretch[] {
  const stretches: PriceStretch[] = [];
  for (const week of weeks) {
    const current = stretches.at(-1);
    if (current?.monthlyRentPaise === week.monthlyRentPaise) {
      current.last = week.moveIn;
    } else {
      stretches.push({
        first: week.moveIn,
        last: week.moveIn,
        monthlyRentPaise: week.monthlyRentPaise,
      });
    }
  }
  return stretches;
}

/** Few enough free beds to say so: 3 or fewer, and at least one. */
export const SCARCE_BEDS = 3;

/** How many beds "only N left" may say, or null when it may not say it. */
export function scarceBeds(bedsFree: number): number | null {
  return bedsFree > 0 && bedsFree <= SCARCE_BEDS ? bedsFree : null;
}
