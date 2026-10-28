"use client";

import { useTranslations } from "next-intl";
import { type ReactNode, useId } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { formatINR } from "@/lib/money";
import {
  GENDERS,
  MEALS,
  OCCUPANCIES,
  RADII_M,
  type SearchQuery,
  type SearchState,
} from "@/lib/search/params";
import { cn } from "@/lib/utils";

import {
  type Amenity,
  CLEARED,
  DEFAULT_RADIUS_M,
  type Locality,
  type MonthOption,
  type Place,
  type SearchPatch,
  selectClasses,
} from "./filters";

// Loaded the first time the filters are opened (ADR 0031), like the other dialogs.

// Budget steps in rupees: thresholds to filter by, not prices (CLAUDE.md rule 12).
const BUDGET_STEPS_RUPEES = [3_000, 5_000, 7_500, 10_000, 12_500, 15_000, 20_000, 25_000, 30_000];
const BUDGET_STEPS_PAISE = BUDGET_STEPS_RUPEES.map((rupees) => rupees * 100);

function Field({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children(id)}
    </div>
  );
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-11 items-center gap-3 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
        className="size-5 shrink-0 accent-primary"
      />
      {label}
    </label>
  );
}

/**
 * Every filter, in a sheet: from the left on a desktop, from the bottom on a phone. Each change
 * goes into the URL at once and the results behind the sheet follow it.
 */
export function FiltersSheet({
  open,
  onOpenChange,
  side,
  state,
  query,
  onChange,
  campuses,
  localities,
  amenities,
  months,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  side: "left" | "bottom";
  state: SearchState;
  query: SearchQuery;
  onChange: (patch: SearchPatch) => void;
  campuses: readonly Place[];
  localities: readonly Locality[];
  amenities: readonly Amenity[];
  months: readonly MonthOption[];
}) {
  const t = useTranslations("Search.filters");
  const tPg = useTranslations("Pg");
  const firstMonth = months[0]?.value;
  const chosen = new Set(query.amenities ?? []);
  const byName = <T extends { name: string }>(items: readonly T[]) =>
    [...items].sort((a, b) => a.name.localeCompare(b.name, "en-IN"));

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={side}
        closeLabel={t("close")}
        // The title says it all; the filters themselves are labelled.
        aria-describedby={undefined}
        className={cn(
          "gap-0",
          side === "bottom" ? "max-h-[85dvh] rounded-t-2xl" : "w-full sm:max-w-md",
        )}
      >
        <SheetHeader className="border-b pe-14">
          <SheetTitle>{t("title")}</SheetTitle>
        </SheetHeader>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain p-4">
          <Field label={t("campus")}>
            {(id) => (
              <select
                id={id}
                value={query.campus ?? ""}
                onChange={(event) => {
                  const campus = event.target.value === "" ? null : event.target.value;
                  onChange({ campus, locality: null, bbox: null });
                }}
                className={selectClasses}
              >
                <option value="">{t("anyCampus")}</option>
                {byName(campuses).map((campus) => (
                  <option key={campus.slug} value={campus.slug}>
                    {campus.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          {query.campus === undefined ? null : (
            <Field label={t("radius")}>
              {(id) => (
                <select
                  id={id}
                  value={String(query.radius_m ?? DEFAULT_RADIUS_M)}
                  onChange={(event) => {
                    const radius = Number(event.target.value);
                    onChange({ radius_m: radius === DEFAULT_RADIUS_M ? null : radius });
                  }}
                  className={selectClasses}
                >
                  {RADII_M.map((radius) => (
                    <option key={radius} value={radius}>
                      {t("radiusKm", { km: radius / 1_000 })}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          )}
          <Field label={t("locality")}>
            {(id) => (
              <select
                id={id}
                value={query.locality ?? ""}
                onChange={(event) => {
                  const locality = event.target.value === "" ? null : event.target.value;
                  onChange({ locality, campus: null, radius_m: null, bbox: null });
                }}
                className={selectClasses}
              >
                <option value="">{t("anyLocality")}</option>
                {byName(localities).map((locality) => (
                  <option key={locality.slug} value={locality.slug}>
                    {locality.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={t("month")}>
            {(id) => (
              <select
                id={id}
                value={query.move_in_month ?? firstMonth ?? ""}
                onChange={(event) => {
                  const month = event.target.value;
                  onChange({ move_in_month: month === firstMonth ? null : month });
                }}
                className={selectClasses}
              >
                {months.map((month) => (
                  <option key={month.value} value={month.value}>
                    {month.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("budgetMin")}>
              {(id) => (
                <select
                  id={id}
                  value={String(query.budget_min_paise ?? "")}
                  onChange={(event) => {
                    onChange({
                      budget_min_paise:
                        event.target.value === "" ? null : Number(event.target.value),
                    });
                  }}
                  className={selectClasses}
                >
                  <option value="">{t("noLimit")}</option>
                  {BUDGET_STEPS_PAISE.filter(
                    (paise) => paise <= (query.budget_max_paise ?? Number.POSITIVE_INFINITY),
                  ).map((paise) => (
                    <option key={paise} value={paise}>
                      {formatINR(paise)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label={t("budgetMax")}>
              {(id) => (
                <select
                  id={id}
                  value={String(query.budget_max_paise ?? "")}
                  onChange={(event) => {
                    onChange({
                      budget_max_paise:
                        event.target.value === "" ? null : Number(event.target.value),
                    });
                  }}
                  className={selectClasses}
                >
                  <option value="">{t("noLimit")}</option>
                  {BUDGET_STEPS_PAISE.filter((paise) => paise >= (query.budget_min_paise ?? 0)).map(
                    (paise) => (
                      <option key={paise} value={paise}>
                        {formatINR(paise)}
                      </option>
                    ),
                  )}
                </select>
              )}
            </Field>
          </div>
          <Field label={t("gender")}>
            {(id) => (
              <select
                id={id}
                value={query.gender ?? ""}
                onChange={(event) => {
                  onChange({
                    gender:
                      event.target.value === ""
                        ? null
                        : (event.target.value as (typeof GENDERS)[number]),
                  });
                }}
                className={selectClasses}
              >
                <option value="">{t("anyGender")}</option>
                {GENDERS.map((gender) => (
                  <option key={gender} value={gender}>
                    {tPg(`gender.${gender}`)}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={t("occupancy")}>
            {(id) => (
              <select
                id={id}
                value={query.occupancy ?? ""}
                onChange={(event) => {
                  onChange({
                    occupancy:
                      event.target.value === ""
                        ? null
                        : (event.target.value as (typeof OCCUPANCIES)[number]),
                  });
                }}
                className={selectClasses}
              >
                <option value="">{t("anyOccupancy")}</option>
                {OCCUPANCIES.map((occupancy) => (
                  <option key={occupancy} value={occupancy}>
                    {tPg(`rooms.sharing.${occupancy}`)}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={t("meals")}>
            {(id) => (
              <select
                id={id}
                value={query.meals ?? ""}
                onChange={(event) => {
                  onChange({
                    meals:
                      event.target.value === ""
                        ? null
                        : (event.target.value as (typeof MEALS)[number]),
                  });
                }}
                className={selectClasses}
              >
                <option value="">{t("anyMeals")}</option>
                {MEALS.map((meals) => (
                  <option key={meals} value={meals}>
                    {tPg(`meals.${meals}`)}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <div>
            <Check
              label={t("ac")}
              checked={query.ac === true}
              onChange={(checked) => {
                onChange({ ac: checked ? true : null });
              }}
            />
            <Check
              label={t("attachedBath")}
              checked={query.attached_bath === true}
              onChange={(checked) => {
                onChange({ attached_bath: checked ? true : null });
              }}
            />
            <Check
              label={t("available")}
              checked={query.available === true}
              onChange={(checked) => {
                onChange({ available: checked ? true : null });
              }}
            />
          </div>
          {amenities.length === 0 ? null : (
            <fieldset>
              <legend className="mb-1 text-sm font-medium">{t("amenities")}</legend>
              <div className="grid grid-cols-1 sm:grid-cols-2">
                {byName(amenities).map((amenity) => (
                  <Check
                    key={amenity.slug}
                    label={amenity.name}
                    checked={chosen.has(amenity.slug)}
                    onChange={(checked) => {
                      const next = new Set(chosen);
                      if (checked) next.add(amenity.slug);
                      else next.delete(amenity.slug);
                      onChange({ amenities: next.size === 0 ? null : [...next] });
                    }}
                  />
                ))}
              </div>
            </fieldset>
          )}
        </div>
        <div className="flex gap-2 border-t p-4">
          <Button
            type="button"
            variant="outline"
            className="flex-1"
            onClick={() => {
              onChange({ ...CLEARED, q: state.q, sort: state.sort });
            }}
          >
            {t("clear")}
          </Button>
          <Button
            type="button"
            className="flex-1"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            {t("showResults")}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
