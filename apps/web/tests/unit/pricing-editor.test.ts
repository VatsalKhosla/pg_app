import { describe, expect, it } from "vitest";

import {
  bodyOf,
  isMonthDayInput,
  isPercent,
  isShare,
  type Rule,
  type RuleValues,
  tiersGoUp,
  valuesOf,
} from "@/components/ops/pricing/rule-values";
import { wholeNumber } from "@/lib/forms/units";
import {
  addDays,
  bpsText,
  dayText,
  isMonthDay,
  monthDayText,
  rentScale,
  shareText,
} from "@/lib/pricing/editor";

const MINUS = "−";

function rule(params: Rule["params"], extra: Partial<Rule> = {}): Rule {
  return {
    id: "0190f0c4-3b1e-7c55-9a1f-1f0e2d3c4b5a",
    position: 0,
    kind: params.kind,
    label: "A rule",
    params,
    roomCategories: null,
    enabled: true,
    ...extra,
  };
}

describe("the editor's words for rules", () => {
  it("shows a rule's change as a signed percentage, with a real minus sign", () => {
    expect([1500, -500, -250, 1, 0].map(bpsText)).toEqual([
      "+15%",
      `${MINUS}5%`,
      `${MINUS}2.5%`,
      "+0.01%",
      "+0%",
    ]);
    expect(shareText(7000)).toBe("70%");
  });

  it("reads a season's days and a move-in as people do", () => {
    expect([monthDayText("08-01"), monthDayText("02-29")]).toEqual(["1 Aug", "29 Feb"]);
    expect([dayText("2027-08-04"), dayText("2027-08-04", { short: true })]).toEqual([
      "4 Aug 2027",
      "4 Aug",
    ]);
  });

  it("counts days on the calendar, across months and a leap year", () => {
    expect(addDays("2027-07-14", 366)).toBe("2028-07-14");
    expect(addDays("2027-12-31", 1)).toBe("2028-01-01");
    expect(addDays("2028-03-01", -1)).toBe("2028-02-29");
  });

  it("knows which days a month has, 29 February included", () => {
    expect([isMonthDay(2, 29), isMonthDay(4, 30), isMonthDay(12, 31)]).toEqual([true, true, true]);
    expect([isMonthDay(2, 30), isMonthDay(4, 31), isMonthDay(13, 1), isMonthDay(1, 0)]).toEqual([
      false,
      false,
      false,
      false,
    ]);
    expect(isMonthDayInput("2", "29")).toBe(true);
  });
});

describe("the price chart's rent axis", () => {
  it("shows every value it's given in round steps", () => {
    expect(rentScale([1_000_000, 1_100_000, 700_000])).toEqual({
      min: 700_000,
      max: 1_100_000,
      ticks: [700_000, 800_000, 900_000, 1_000_000, 1_100_000],
    });
  });

  it("puts a flat price mid-chart", () => {
    expect(rentScale([1_000_000, 1_000_000])).toEqual({
      min: 950_000,
      max: 1_050_000,
      ticks: [950_000, 1_000_000, 1_050_000],
    });
  });

  it("widens its step for a wide range", () => {
    const scale = rentScale([600_000, 2_500_000]);
    expect(scale.ticks.length).toBeLessThanOrEqual(6);
    expect(scale.min).toBeLessThanOrEqual(600_000);
    expect(scale.max).toBeGreaterThanOrEqual(2_500_000);
  });
});

describe("a rule's form values", () => {
  it.each<[string, Rule["params"]]>([
    ["a season up", { kind: "season", start: "08-01", end: "08-31", bps: 1500 }],
    [
      "a season down, across the new year",
      { kind: "season", start: "12-15", end: "01-15", bps: -1000 },
    ],
    ["early-bird", { kind: "early_bird", minDaysBefore: 30, bps: -500 }],
    ["last-minute", { kind: "last_minute", maxDaysBefore: 7, maxOccupancyBps: 5000, bps: -750 }],
    [
      "occupancy",
      {
        kind: "occupancy",
        tiers: [
          { minOccupancyBps: 7000, bps: 500 },
          { minOccupancyBps: 9000, bps: 1000 },
        ],
      },
    ],
    [
      "length of stay",
      {
        kind: "length_of_stay",
        tiers: [
          { minMonths: 6, bps: -300 },
          { minMonths: 11, bps: -700 },
        ],
      },
    ],
    [
      "a fixed rent",
      { kind: "override", start: "2027-06-15", end: "2027-07-15", rentPaise: 950_000 },
    ],
  ])("go back to the API as they came: %s", (_, params) => {
    const original = rule(params, { roomCategories: [{ id: "room-1", label: "Double sharing" }] });

    expect(bodyOf(valuesOf(original))).toEqual({
      label: "A rule",
      params,
      roomCategories: ["room-1"],
      enabled: true,
    });
  });

  it("ask discounts as discounts and a season's direction, so nobody types a minus sign", () => {
    const values: RuleValues = {
      ...valuesOf(),
      kind: "season",
      label: "  Monsoon  ",
      startMonth: "7",
      startDay: "1",
      endMonth: "9",
      endDay: "30",
      direction: "down",
      percent: "5",
    };

    expect(bodyOf(values)).toEqual({
      label: "Monsoon",
      params: { kind: "season", start: "07-01", end: "09-30", bps: -500 },
      roomCategories: null,
      enabled: true,
    });
    expect(bodyOf({ ...values, kind: "early_bird", days: "45", percent: "2.5" }).params).toEqual({
      kind: "early_bird",
      minDaysBefore: 45,
      bps: -250,
    });
  });

  it("check what the API checks", () => {
    expect([isPercent("15"), isPercent("100"), isPercent("0"), isPercent("101")]).toEqual([
      true,
      true,
      false,
      false,
    ]);
    expect([isShare("0"), isShare("99.99"), isShare("100")]).toEqual([true, true, false]);
    const rows = (...starts: string[]) => starts.map((from) => ({ from, percent: "5" }));
    expect(tiersGoUp(rows("6", "11"), wholeNumber)).toBe(true);
    expect(tiersGoUp(rows("11", "6"), wholeNumber)).toBe(false);
    expect(tiersGoUp(rows("6", "6"), wholeNumber)).toBe(false);
    expect(tiersGoUp(rows("6", ""), wholeNumber)).toBe(false);
  });
});
