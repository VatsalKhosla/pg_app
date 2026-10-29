import { describe, expect, it } from "vitest";

import { priceStretches, scarceBeds } from "@/lib/pricing/calendar";

const week = (moveIn: string, rupees: number) => ({ moveIn, monthlyRentPaise: rupees * 100 });

describe("price changes the PG page may show", () => {
  it("come only from where the calendar's price changes", () => {
    expect(
      priceStretches([
        week("2027-06-01", 9_500),
        week("2027-06-08", 9_500),
        week("2027-06-15", 9_500),
        week("2027-06-22", 11_000),
        week("2027-06-29", 11_000),
      ]),
    ).toEqual([
      { first: "2027-06-01", last: "2027-06-15", monthlyRentPaise: 950_000 },
      { first: "2027-06-22", last: "2027-06-29", monthlyRentPaise: 1_100_000 },
    ]);
  });

  it("are none when the price stays the same", () => {
    expect(priceStretches([week("2027-06-01", 9_500), week("2027-06-08", 9_500)])).toHaveLength(1);
    expect(priceStretches([])).toEqual([]);
  });

  it("follow the price back down as well as up", () => {
    expect(
      priceStretches([
        week("2027-08-24", 11_500),
        week("2027-08-31", 11_500),
        week("2027-09-07", 10_000),
      ]).map((stretch) => stretch.monthlyRentPaise),
    ).toEqual([1_150_000, 1_000_000]);
  });
});

describe("scarcity the PG page may show", () => {
  it("is only for 1 to 3 free beds", () => {
    expect([0, 1, 2, 3, 4, 12].map(scarceBeds)).toEqual([null, 1, 2, 3, null, null]);
  });
});
