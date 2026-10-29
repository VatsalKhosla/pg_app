import { describe, expect, it } from "vitest";

import { bpsToPercentInput, percentToBps, wholeNumber } from "@/lib/admin/units";

describe("percentages on the admin forms", () => {
  it.each([
    ["30", 3000],
    ["18.5", 1850],
    ["0.25", 25],
    ["40 %", 4000],
    ["100", 10000],
  ])("%s%% is %i basis points", (input, bps) => {
    expect(percentToBps(input)).toBe(bps);
  });

  it.each(["", "thirty", "1.234", "-5", "1e3"])("%s isn't a percentage", (input) => {
    expect(percentToBps(input)).toBeNull();
  });

  it("show basis points as the admin would type them", () => {
    expect([3000, 1850, 25, 0, 10000].map(bpsToPercentInput)).toEqual([
      "30",
      "18.5",
      "0.25",
      "0",
      "100",
    ]);
    for (const bps of [3000, 1850, 25, 1, 9999]) {
      expect(percentToBps(bpsToPercentInput(bps))).toBe(bps);
    }
  });
});

describe("whole numbers on the admin forms", () => {
  it("are digits only", () => {
    expect(wholeNumber(" 15 ")).toBe(15);
    expect(wholeNumber("1.5")).toBeNull();
    expect(wholeNumber("")).toBeNull();
    expect(wholeNumber("-1")).toBeNull();
  });
});
