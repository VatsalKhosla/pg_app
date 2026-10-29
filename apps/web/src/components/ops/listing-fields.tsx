"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";
import { type DefaultValues, type UseFormReturn, useWatch } from "react-hook-form";

import { type LatLng, NCR_BOUNDS } from "@/components/map/map-provider";
import { Input } from "@/components/ui/input";
import { z } from "@/lib/forms/zod";
import type { Listing, PropertyCreate, PropertyUpdate } from "@/lib/ops/client";

import {
  GENDER_POLICIES,
  LICENCE_STATUSES,
  MEALS,
  PRECISIONS,
  SOCIETY_PERMISSIONS,
} from "./choices";
import { Checkbox, Choices, Field, Select, Textarea } from "@/components/ui/fields";
import { formatCoordinate, parseCoordinate, PinField, pinOf } from "./pin-field";

/**
 * The API's own limits, checked here first: apps/api/src/app/modules/catalog/domain/listing.py and
 * service/checks.py (stricter than its request schema's).
 */
const NAME_MAX = 120;
const ADDRESS_MAX = 300;
const DESCRIPTION_MAX = 5_000;
const RULE_MAX = 200;
const RULES_MAX = 30;
const LICENCE_NUMBER_MAX = 60;

export interface DetailsMessages {
  required: string;
  choose: string;
  tooLong: string;
  coordinate: string;
  outside: string;
  rules: string;
}

/** House rules as ops type them: one a line, blank lines dropped. */
export function rulesOf(text: string): string[] {
  return text
    .split("\n")
    .map((rule) => rule.trim())
    .filter((rule) => rule !== "");
}

function within(text: string, low: number, high: number): boolean {
  const value = parseCoordinate(text);
  return value !== null && low <= value && value <= high;
}

/** A listing's details as the form holds them; the new-listing form adds the locality. */
export function detailsShape(m: DetailsMessages) {
  return {
    // Chosen when the listing is made, and fixed after (the API takes it only then).
    locality: z.string().min(1, m.choose),
    name: z.string().trim().min(1, m.required).max(NAME_MAX, m.tooLong),
    addressLine: z.string().trim().min(1, m.required).max(ADDRESS_MAX, m.tooLong),
    lat: z
      .string()
      .refine((text) => parseCoordinate(text) !== null, m.coordinate)
      .refine((text) => within(text, NCR_BOUNDS.south, NCR_BOUNDS.north), m.outside),
    lng: z
      .string()
      .refine((text) => parseCoordinate(text) !== null, m.coordinate)
      .refine((text) => within(text, NCR_BOUNDS.west, NCR_BOUNDS.east), m.outside),
    locationPrecision: z.enum(PRECISIONS, { error: m.choose }),
    genderPolicy: z.enum(GENDER_POLICIES, { error: m.choose }),
    meals: z.enum(MEALS, { error: m.choose }),
    description: z.string().max(DESCRIPTION_MAX, m.tooLong),
    houseRules: z.string().refine((text) => {
      const rules = rulesOf(text);
      return rules.length <= RULES_MAX && rules.every((rule) => rule.length <= RULE_MAX);
    }, m.rules),
    licenceStatus: z.enum(LICENCE_STATUSES),
    licenceNumber: z.string().trim().max(LICENCE_NUMBER_MAX, m.tooLong),
    societyPermission: z.enum(SOCIETY_PERMISSIONS),
    instantConfirm: z.boolean(),
  };
}

export type DetailsValues = z.infer<z.ZodObject<ReturnType<typeof detailsShape>>>;

export function useDetailsMessages(): DetailsMessages {
  const t = useTranslations("Ops.validation");
  return {
    required: t("required"),
    choose: t("choose"),
    tooLong: t("tooLong"),
    coordinate: t("coordinate"),
    outside: t("outside"),
    rules: t("rules", { count: RULES_MAX, length: RULE_MAX }),
  };
}

/**
 * The form's starting values: the listing's, or a new listing's. Who it's for, meals and how
 * exact the pin is start unchosen, so ops pick each on purpose.
 */
export function detailsDefaults(listing?: Listing): DefaultValues<DetailsValues> {
  if (listing === undefined) {
    return {
      locality: "",
      name: "",
      addressLine: "",
      lat: "",
      lng: "",
      description: "",
      houseRules: "",
      licenceStatus: "unknown",
      licenceNumber: "",
      societyPermission: "n/a",
      instantConfirm: false,
    };
  }
  return {
    locality: listing.locality.slug,
    name: listing.name,
    addressLine: listing.addressLine,
    lat: formatCoordinate(listing.location.lat),
    lng: formatCoordinate(listing.location.lng),
    locationPrecision: listing.locationPrecision,
    genderPolicy: listing.genderPolicy,
    meals: listing.meals,
    description: listing.description,
    houseRules: listing.houseRules.join("\n"),
    licenceStatus: listing.licenceStatus,
    licenceNumber: listing.licenceNumber ?? "",
    societyPermission: listing.societyPermission,
    instantConfirm: listing.instantConfirm,
  };
}

type DetailsBody = Required<Omit<PropertyCreate, "owner" | "locality">>;

/** The details as the API takes them. */
export function detailsBody(values: DetailsValues): DetailsBody {
  const licenceNumber = values.licenceNumber.trim();
  return {
    name: values.name,
    addressLine: values.addressLine,
    location: { lat: Number(values.lat), lng: Number(values.lng) },
    locationPrecision: values.locationPrecision,
    genderPolicy: values.genderPolicy,
    meals: values.meals,
    description: values.description.trim(),
    houseRules: rulesOf(values.houseRules),
    licenceStatus: values.licenceStatus,
    licenceNumber: licenceNumber === "" ? null : licenceNumber,
    societyPermission: values.societyPermission,
    instantConfirm: values.instantConfirm,
  };
}

/** Which part of the API's body each form field fills. */
const BODY_FIELD = {
  name: "name",
  addressLine: "addressLine",
  lat: "location",
  lng: "location",
  locationPrecision: "locationPrecision",
  genderPolicy: "genderPolicy",
  meals: "meals",
  description: "description",
  houseRules: "houseRules",
  licenceStatus: "licenceStatus",
  licenceNumber: "licenceNumber",
  societyPermission: "societyPermission",
  instantConfirm: "instantConfirm",
} as const satisfies Record<Exclude<keyof DetailsValues, "locality">, keyof DetailsBody>;

type BodyField = keyof typeof BODY_FIELD;

/**
 * Only what ops changed, so the listing's history says what really changed (the API records the
 * fields it was sent) and an untouched pin keeps its public point.
 */
export function changedDetails(
  values: DetailsValues,
  dirty: Partial<Record<keyof DetailsValues, unknown>>,
): PropertyUpdate {
  const body = detailsBody(values);
  const changes: PropertyUpdate = {};
  for (const field of Object.keys(BODY_FIELD) as BodyField[]) {
    const sent = BODY_FIELD[field];
    if (dirty[field] === true) Object.assign(changes, { [sent]: body[sent] });
  }
  return changes;
}

/** The form field an API error points at (`/location/lat`, `/houseRules/3`, `/name`). */
export function detailsFieldFor(pointer: string): keyof DetailsValues | undefined {
  const [, first, second] = pointer.split("/");
  if (first === "location") return second === "lng" ? "lng" : "lat";
  if (first === "locality") return "locality";
  return (Object.keys(BODY_FIELD) as BodyField[]).find((field) => field === first);
}

export interface LocalityChoice {
  slug: string;
  name: string;
  center: LatLng;
}

export interface CityChoice {
  name: string;
  localities: LocalityChoice[];
}

/**
 * A listing's details: what students will see, and where it is. With `cities`, the locality is
 * chosen too (a new listing), and the map looks there until the pin is placed.
 */
export function ListingFields({
  form,
  cities,
}: {
  form: UseFormReturn<DetailsValues>;
  cities?: CityChoice[];
}) {
  const t = useTranslations("Ops");
  const id = useId();
  const { errors } = form.formState;
  const [lat, lng, locality] = useWatch({
    control: form.control,
    name: ["lat", "lng", "locality"],
  });
  const center = cities
    ?.flatMap((city) => city.localities)
    .find((choice) => choice.slug === locality)?.center;

  function setPin(pin: LatLng) {
    const options = { shouldDirty: true, shouldValidate: true } as const;
    form.setValue("lat", formatCoordinate(pin.lat), options);
    form.setValue("lng", formatCoordinate(pin.lng), options);
  }

  return (
    <div className="space-y-6">
      {cities === undefined ? null : (
        <Field id={`${id}-locality`} label={t("details.locality")} error={errors.locality?.message}>
          {(control) => (
            <Select {...control} {...form.register("locality")}>
              <option value="">{t("details.localityChoose")}</option>
              {cities.map((city) => (
                <optgroup key={city.name} label={city.name}>
                  {city.localities.map((choice) => (
                    <option key={choice.slug} value={choice.slug}>
                      {choice.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          )}
        </Field>
      )}
      <Field id={`${id}-name`} label={t("details.name")} error={errors.name?.message}>
        {(control) => <Input {...control} autoComplete="off" {...form.register("name")} />}
      </Field>
      <Field
        id={`${id}-address`}
        label={t("details.address")}
        hint={t("details.addressHint")}
        error={errors.addressLine?.message}
      >
        {(control) => <Textarea {...control} rows={2} {...form.register("addressLine")} />}
      </Field>
      <PinField
        id={`${id}-pin`}
        lat={form.register("lat")}
        lng={form.register("lng")}
        pin={pinOf(lat, lng)}
        onPin={setPin}
        center={center}
        errors={{ lat: errors.lat?.message, lng: errors.lng?.message }}
      />
      <Choices
        id={`${id}-precision`}
        legend={t("pin.precision")}
        options={PRECISIONS.map((value) => ({ value, label: t(`precision.${value}`) }))}
        registration={form.register("locationPrecision")}
        error={errors.locationPrecision?.message}
      />
      <Choices
        id={`${id}-gender`}
        legend={t("details.gender")}
        options={GENDER_POLICIES.map((value) => ({ value, label: t(`gender.${value}`) }))}
        registration={form.register("genderPolicy")}
        error={errors.genderPolicy?.message}
        columns={3}
      />
      <Choices
        id={`${id}-meals`}
        legend={t("details.meals")}
        options={MEALS.map((value) => ({ value, label: t(`meals.${value}`) }))}
        registration={form.register("meals")}
        error={errors.meals?.message}
        columns={3}
      />
      <Field
        id={`${id}-description`}
        label={t("details.description")}
        hint={t("details.descriptionHint")}
        error={errors.description?.message}
      >
        {(control) => <Textarea {...control} rows={5} {...form.register("description")} />}
      </Field>
      <Field
        id={`${id}-rules`}
        label={t("details.houseRules")}
        hint={t("details.houseRulesHint")}
        error={errors.houseRules?.message}
      >
        {(control) => <Textarea {...control} rows={4} {...form.register("houseRules")} />}
      </Field>
      <div className="grid gap-6 sm:grid-cols-2">
        <Field id={`${id}-licence`} label={t("details.licence")}>
          {(control) => (
            <Select {...control} {...form.register("licenceStatus")}>
              {LICENCE_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {t(`licence.${value}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field
          id={`${id}-licence-number`}
          label={t("details.licenceNumber")}
          error={errors.licenceNumber?.message}
        >
          {(control) => (
            <Input {...control} autoComplete="off" {...form.register("licenceNumber")} />
          )}
        </Field>
      </div>
      <Field id={`${id}-society`} label={t("details.society")}>
        {(control) => (
          <Select {...control} {...form.register("societyPermission")}>
            {SOCIETY_PERMISSIONS.map((value) => (
              <option key={value} value={value}>
                {t(`society.${value}`)}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Checkbox label={t("details.instantConfirm")} {...form.register("instantConfirm")} />
    </div>
  );
}
