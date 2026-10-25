import type { Schemas } from "@pg-platform/api-client";

import { valuesOf } from "@/lib/forms/options";

/** The API's enums the console offers as choices, every value of each (see valuesOf). */

export type GenderPolicy = Schemas["GenderPolicy"];
export type Meals = Schemas["Meals"];
export type LicenceStatus = Schemas["LicenceStatus"];
export type SocietyPermission = Schemas["SocietyPermission"];
export type LocationPrecision = Schemas["LocationPrecision"];
export type Occupancy = Schemas["Occupancy"];
export type ChargeKind = Schemas["ChargeKind"];
export type ChargeType = Schemas["CategoryCreate"]["mandatoryCharges"][number]["type"];
export type ListingStatus = Schemas["PropertyStatus"];

export const GENDER_POLICIES = valuesOf<GenderPolicy>({ boys: true, girls: true, coed: true });
export const MEALS = valuesOf<Meals>({
  none: true,
  breakfast: true,
  two: true,
  three: true,
  four: true,
});
export const LICENCE_STATUSES = valuesOf<LicenceStatus>({
  unknown: true,
  applied: true,
  licensed: true,
  not_required: true,
});
export const SOCIETY_PERMISSIONS = valuesOf<SocietyPermission>({
  "n/a": true,
  on_file: true,
  missing: true,
});
export const PRECISIONS = valuesOf<LocationPrecision>({ exact: true, approximate: true });
export const OCCUPANCIES = valuesOf<Occupancy>({
  single: true,
  double: true,
  triple: true,
  quad: true,
});
export const CHARGE_TYPES = valuesOf<ChargeType>({ monthly: true, metered: true, oneTime: true });
export const CHARGE_KINDS = valuesOf<ChargeKind>({
  electricity: true,
  water: true,
  maintenance: true,
  internet: true,
  laundry: true,
  food: true,
  registration: true,
  other: true,
});
export const LISTING_STATUSES = valuesOf<ListingStatus>({
  draft: true,
  published: true,
  paused: true,
  delisted: true,
});

export function isListingStatus(value: unknown): value is ListingStatus {
  return typeof value === "string" && (LISTING_STATUSES as readonly string[]).includes(value);
}
