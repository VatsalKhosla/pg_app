import type { Schemas } from "@pg-platform/api-client";

import { type LatLng, roundCoordinate } from "@/components/map/map-provider";
import { valuesOf } from "@/lib/forms/options";

/**
 * A verification report as its form holds it, and as the API takes it (ADR 0024). Yes-or-no
 * questions are radio buttons that start unanswered, so the agent answers each one.
 */

export type Condition = Schemas["Condition"];
export type Cracks = Schemas["Cracks"];
export type WomenSafety = Schemas["WomenSafety"];
export type VisitResult = Schemas["VisitResult"];
export type SocietyPermission = Schemas["SocietyPermission"];
export type ReportBody = Schemas["ReportSubmit"];

export const CONDITIONS = valuesOf<Condition>({ good: true, fair: true, poor: true });
export const CRACKS = valuesOf<Cracks>({ none: true, minor: true, structural: true });
export const WOMEN_SAFETY = valuesOf<WomenSafety>({
  woman_staff: true,
  secure_entry: true,
  lit_approach: true,
  visitor_log: true,
  separate_floors: true,
});
export const RESULTS = valuesOf<VisitResult>({ passed: true, failed: true });
export const ANSWERS = valuesOf<"yes" | "no">({ yes: true, no: true });

/** The API's limits (apps/api/src/app/modules/catalog/domain/verification.py). */
export const OLDEST_BUILDING_YEARS = 200;
export const MOST_EXITS = 20;
export const NOTES_MAX = 2_000;
export const LICENCE_NUMBER_MAX = 100;
export const MAX_PHOTOS = 20;

export interface ReportValues {
  age: string;
  condition: Condition;
  cracks: Cracks;
  exits: string;
  fireExtinguishers: "yes" | "no";
  cctv: "yes" | "no";
  warden: "yes" | "no";
  womenSafety: WomenSafety[];
  licenceNumber: string;
  societyPermission: SocietyPermission;
  authorityNotice: "yes" | "no";
  result: VisitResult;
  notes: string;
  movePin: boolean;
}

/** Where the phone said the agent was, and how sure it was. */
export interface Fix {
  position: LatLng;
  accuracyM: number;
}

/** A whole number from `low` to `high`, as typed; null for anything else. */
export function wholeNumber(text: string, low: number, high: number): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,3}$/u.test(trimmed)) return null;
  const value = Number(trimmed);
  return low <= value && value <= high ? value : null;
}

export function reportBody(values: ReportValues, fix: Fix, photos: readonly string[]): ReportBody {
  const licenceNumber = values.licenceNumber.trim();
  return {
    checklist: {
      buildingAgeYears:
        values.age.trim() === "" ? null : wholeNumber(values.age, 0, OLDEST_BUILDING_YEARS),
      condition: values.condition,
      cracks: values.cracks,
      exits: wholeNumber(values.exits, 0, MOST_EXITS) ?? 0,
      fireExtinguishers: values.fireExtinguishers === "yes",
      cctv: values.cctv === "yes",
      warden: values.warden === "yes",
      womenSafety: [...values.womenSafety].sort(),
      licenceNumber: licenceNumber === "" ? null : licenceNumber,
      societyPermission: values.societyPermission,
      authorityNotice: values.authorityNotice === "yes",
    },
    result: values.result,
    notes: values.notes.trim(),
    position: {
      lat: roundCoordinate(fix.position.lat),
      lng: roundCoordinate(fix.position.lng),
    },
    accuracyM: Math.round(fix.accuracyM),
    photos: [...photos],
    movePin: values.movePin,
  };
}
