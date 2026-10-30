import type { Schemas } from "@pg-platform/api-client";

import { bpsToPercentInput, percentToBps, wholeNumber } from "@/lib/forms/units";
import { paiseToRupeesInput, rupeesToPaise } from "@/lib/money";
import { isMonthDay } from "@/lib/pricing/editor";

/**
 * A pricing rule as its form holds it (percentages, days and rupees as typed) and as the API
 * takes it (basis points and paise; step 4.6, ADR 0041). The form asks which way a season moves
 * the rent and asks the discounts as discounts, so nobody has to type a minus sign; the API
 * checks every rule again.
 */

export type Rule = Schemas["PricingRuleInfo"];
export type RuleInput = Schemas["PricingRuleInput"];
type Params = RuleInput["params"];
export type RuleKind = Params["kind"];

/** In the order the form offers them: the common ones first. */
export const RULE_KINDS = [
  "season",
  "early_bird",
  "length_of_stay",
  "last_minute",
  "occupancy",
  "override",
] as const satisfies readonly RuleKind[];

export const MONTHS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"] as const;

export interface TierRow {
  /** Occupancy: from this % of beds taken. Length of stay: from this many months. */
  from: string;
  percent: string;
}

export interface RuleValues {
  kind: RuleKind;
  label: string;
  /** "all" is every room, including any added later; "some" is `roomIds` only. */
  rooms: "all" | "some";
  roomIds: string[];
  enabled: boolean;
  startMonth: string;
  startDay: string;
  endMonth: string;
  endDay: string;
  direction: "up" | "down";
  /** A season's change, or early-bird's or last-minute's discount, as a percentage. */
  percent: string;
  /** Early-bird's fewest days ahead, or last-minute's most. */
  days: string;
  /** Last-minute's most beds taken, as a percentage. */
  maxTaken: string;
  tiers: TierRow[];
  startDate: string;
  endDate: string;
  rent: string;
}

export const NEW_TIER: TierRow = { from: "", percent: "" };

const EMPTY: RuleValues = {
  kind: "season",
  label: "",
  rooms: "all",
  roomIds: [],
  enabled: true,
  startMonth: "",
  startDay: "",
  endMonth: "",
  endDay: "",
  direction: "up",
  percent: "",
  days: "",
  maxTaken: "",
  tiers: [{ ...NEW_TIER }],
  startDate: "",
  endDate: "",
  rent: "",
};

function monthDayParts(monthDay: string): [string, string] {
  const [month = "", day = ""] = monthDay.split("-");
  return [String(Number(month)), String(Number(day))];
}

function monthDay(month: string, day: string): string {
  return `${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

/** A positive percentage up to 100, as typed. */
export function isPercent(
  text: string,
  { below100 = false }: { below100?: boolean } = {},
): boolean {
  const bps = percentToBps(text);
  return bps !== null && bps > 0 && (below100 ? bps < 10_000 : bps <= 10_000);
}

/** A percentage from 0 up to but not including 100: last-minute's most beds taken. */
export function isShare(text: string): boolean {
  const bps = percentToBps(text);
  return bps !== null && bps < 10_000;
}

/** A whole number from `min` to `max`, as typed. */
export function isWhole(text: string, min: number, max: number): boolean {
  const number = wholeNumber(text);
  return number !== null && number >= min && number <= max;
}

/** Whether a month and day typed make a real day. */
export function isMonthDayInput(month: string, day: string): boolean {
  return isMonthDay(Number(month), Number(day));
}

/** Tiers' starts go up, each its own: what the API asks of occupancy and stay tiers. */
export function tiersGoUp(
  rows: readonly TierRow[],
  parse: (text: string) => number | null,
): boolean {
  const starts = rows.map((row) => parse(row.from));
  return starts.every(
    (start, index) =>
      start !== null && (index === 0 || start > (starts[index - 1] ?? Number.POSITIVE_INFINITY)),
  );
}

/** The form's starting values: a new rule's, or `rule`'s as it is. */
export function valuesOf(rule?: Rule): RuleValues {
  if (rule === undefined) return { ...EMPTY, tiers: [{ ...NEW_TIER }] };
  const values: RuleValues = {
    ...EMPTY,
    kind: rule.params.kind,
    label: rule.label,
    rooms: rule.roomCategories === null ? "all" : "some",
    roomIds: rule.roomCategories?.map((category) => category.id) ?? [],
    enabled: rule.enabled,
    tiers: [],
  };
  const params = rule.params;
  switch (params.kind) {
    case "season": {
      const [startMonth, startDay] = monthDayParts(params.start);
      const [endMonth, endDay] = monthDayParts(params.end);
      return {
        ...values,
        startMonth,
        startDay,
        endMonth,
        endDay,
        direction: params.bps < 0 ? "down" : "up",
        percent: bpsToPercentInput(Math.abs(params.bps)),
      };
    }
    case "early_bird":
      return {
        ...values,
        days: String(params.minDaysBefore),
        percent: bpsToPercentInput(-params.bps),
      };
    case "last_minute":
      return {
        ...values,
        days: String(params.maxDaysBefore),
        maxTaken: bpsToPercentInput(params.maxOccupancyBps),
        percent: bpsToPercentInput(-params.bps),
      };
    case "occupancy":
      return {
        ...values,
        tiers: params.tiers.map((tier) => ({
          from: bpsToPercentInput(tier.minOccupancyBps),
          percent: bpsToPercentInput(tier.bps),
        })),
      };
    case "length_of_stay":
      return {
        ...values,
        tiers: params.tiers.map((tier) => ({
          from: String(tier.minMonths),
          percent: bpsToPercentInput(-tier.bps),
        })),
      };
    case "override":
      return {
        ...values,
        startDate: params.start,
        endDate: params.end,
        rent: paiseToRupeesInput(params.rentPaise),
      };
  }
}

function bps(text: string): number {
  return percentToBps(text) ?? 0;
}

function whole(text: string): number {
  return wholeNumber(text) ?? 0;
}

/** What the API takes for checked `values`: only the fields of the rule's kind. */
export function bodyOf(values: RuleValues): RuleInput {
  return {
    label: values.label.trim(),
    params: paramsOf(values),
    roomCategories: values.rooms === "all" ? null : values.roomIds,
    enabled: values.enabled,
  };
}

function paramsOf(values: RuleValues): Params {
  switch (values.kind) {
    case "season":
      return {
        kind: "season",
        start: monthDay(values.startMonth, values.startDay),
        end: monthDay(values.endMonth, values.endDay),
        bps: values.direction === "down" ? -bps(values.percent) : bps(values.percent),
      };
    case "early_bird":
      return { kind: "early_bird", minDaysBefore: whole(values.days), bps: -bps(values.percent) };
    case "last_minute":
      return {
        kind: "last_minute",
        maxDaysBefore: whole(values.days),
        maxOccupancyBps: bps(values.maxTaken),
        bps: -bps(values.percent),
      };
    case "occupancy":
      return {
        kind: "occupancy",
        tiers: values.tiers.map((tier) => ({
          minOccupancyBps: bps(tier.from),
          bps: bps(tier.percent),
        })),
      };
    case "length_of_stay":
      return {
        kind: "length_of_stay",
        tiers: values.tiers.map((tier) => ({
          minMonths: whole(tier.from),
          bps: -bps(tier.percent),
        })),
      };
    case "override":
      return {
        kind: "override",
        start: values.startDate,
        end: values.endDate,
        rentPaise: rupeesToPaise(values.rent) ?? 0,
      };
  }
}

/** Where the API's field errors land: its JSON pointers to the form's fields. */
export function fieldFor(pointer: string): keyof RuleValues | undefined {
  if (pointer === "/label") return "label";
  if (pointer.startsWith("/roomCategories")) return "roomIds";
  return undefined;
}
