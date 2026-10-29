"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";
import { addCategory, updateCategory } from "@/lib/ops/client";

import {
  bodyOf,
  type Category,
  type CategoryValues,
  changesOf,
  type ChargeRow,
  defaultsOf,
  isAmount,
  NEW_CHARGE,
  POINTER_FIELDS,
} from "./category-values";

import { CHARGE_KINDS, CHARGE_TYPES, OCCUPANCIES } from "./choices";
import { Checkbox, Choices, Field, FormOutcome, Select } from "@/components/ui/fields";
import { useOpsProblem } from "./problems";
import { useRefresh } from "./use-refresh";

/** The API's limits (apps/api/src/app/modules/catalog/domain/rooms.py and charges.py). */
const LABEL_MAX = 80;
const CHARGE_LABEL_MAX = 60;
const UNIT_MAX = 16;
const CHARGES_MAX = 12;

function categorySchema(
  t: ReturnType<typeof useTranslations<"Ops">>,
): z.ZodType<CategoryValues, CategoryValues> {
  const required = t("validation.required");
  const tooLong = t("validation.tooLong");
  const amount = t("validation.amount");
  const optionalAmount = z
    .string()
    .refine((text) => text.trim() === "" || isAmount(text, { zero: false }), amount);
  const charge = z
    .object({
      type: z.enum(CHARGE_TYPES),
      kind: z.enum(CHARGE_KINDS),
      label: z.string().trim().min(1, required).max(CHARGE_LABEL_MAX, tooLong),
      amount: z.string(),
      rate: z.string(),
      unit: z.string().trim().max(UNIT_MAX, tooLong),
      estimate: z.string(),
    })
    .refine((row) => row.type === "metered" || isAmount(row.amount, { zero: false }), {
      message: amount,
      path: ["amount"],
    })
    .refine((row) => row.type !== "metered" || isAmount(row.rate, { zero: false }), {
      message: amount,
      path: ["rate"],
    })
    .refine((row) => row.type !== "metered" || row.unit.trim() !== "", {
      message: required,
      path: ["unit"],
    })
    .refine((row) => row.type !== "metered" || isAmount(row.estimate, { zero: false }), {
      message: amount,
      path: ["estimate"],
    });
  return z.object({
    occupancy: z.enum(OCCUPANCIES, { error: t("validation.choose") }),
    label: z.string().trim().min(1, required).max(LABEL_MAX, tooLong),
    ac: z.boolean(),
    attachedBath: z.boolean(),
    balcony: z.boolean(),
    baseRent: z.string().refine((text) => isAmount(text, { zero: false }), amount),
    ownerMin: optionalAmount,
    ownerMax: optionalAmount,
    deposit: z.string().refine((text) => isAmount(text, { zero: true }), amount),
    charges: z.array(charge).max(CHARGES_MAX),
  });
}

/** A charge row's field, as React Hook Form names it. */
function chargeField<K extends keyof ChargeRow>(index: number, key: K): `charges.${number}.${K}` {
  return `charges.${index.toString()}.${key}` as `charges.${number}.${K}`;
}

/**
 * A room category: what students choose and what the rent is set for, with every charge they'll
 * pay besides the rent. New (for `listingId`) or an existing one to edit; its sharing is fixed
 * once rooms are made for it.
 */
export function CategoryForm({
  listingId,
  category,
  onDone,
}: {
  listingId: string;
  category?: Category;
  onDone: () => void;
}) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const form = useForm<CategoryValues>({
    resolver: zodResolver(categorySchema(t)),
    defaultValues: defaultsOf(category),
  });
  const charges = useFieldArray({ control: form.control, name: "charges" });
  const types = useWatch({ control: form.control, name: "charges" }).map((row) => row.type);
  const { errors, isSubmitting } = form.formState;

  async function save(values: CategoryValues) {
    setFailure(null);
    const body = bodyOf(values);
    try {
      if (category === undefined) {
        await addCategory(listingId, body);
      } else {
        const changes = changesOf(category, body);
        if (Object.keys(changes).length > 0) await updateCategory(category.id, changes);
      }
      refresh();
      onDone();
    } catch (error) {
      const shown = showFieldErrors(error, form.setError, (pointer) =>
        pointer.startsWith("/mandatoryCharges")
          ? undefined
          : POINTER_FIELDS[pointer as keyof typeof POINTER_FIELDS],
      );
      if (!shown) setFailure(problem(error));
    }
  }

  return (
    <form
      noValidate
      className="space-y-6 rounded-md border p-4"
      onSubmit={(event) => {
        void form.handleSubmit(save)(event);
      }}
    >
      {category === undefined ? (
        <Choices
          id={`${id}-occupancy`}
          legend={t("rooms.occupancy")}
          options={OCCUPANCIES.map((value) => ({ value, label: t(`occupancy.${value}`) }))}
          registration={form.register("occupancy")}
          error={errors.occupancy?.message}
        />
      ) : null}
      <Field
        id={`${id}-label`}
        label={t("rooms.label")}
        hint={t("rooms.labelHint")}
        error={errors.label?.message}
      >
        {(control) => <Input {...control} autoComplete="off" {...form.register("label")} />}
      </Field>
      <div className="flex flex-wrap gap-x-6">
        <Checkbox label={t("rooms.ac")} {...form.register("ac")} />
        <Checkbox label={t("rooms.attachedBath")} {...form.register("attachedBath")} />
        <Checkbox label={t("rooms.balcony")} {...form.register("balcony")} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          id={`${id}-rent`}
          label={t("rooms.baseRent")}
          hint={t("rooms.baseRentHint")}
          error={errors.baseRent?.message}
          className="sm:col-span-2"
        >
          {(control) => (
            <Input
              {...control}
              inputMode="decimal"
              autoComplete="off"
              {...form.register("baseRent")}
            />
          )}
        </Field>
        <Field id={`${id}-min`} label={t("rooms.ownerMin")} error={errors.ownerMin?.message}>
          {(control) => (
            <Input
              {...control}
              inputMode="decimal"
              autoComplete="off"
              {...form.register("ownerMin")}
            />
          )}
        </Field>
        <Field id={`${id}-max`} label={t("rooms.ownerMax")} error={errors.ownerMax?.message}>
          {(control) => (
            <Input
              {...control}
              inputMode="decimal"
              autoComplete="off"
              {...form.register("ownerMax")}
            />
          )}
        </Field>
        <Field id={`${id}-deposit`} label={t("rooms.deposit")} error={errors.deposit?.message}>
          {(control) => (
            <Input
              {...control}
              inputMode="decimal"
              autoComplete="off"
              {...form.register("deposit")}
            />
          )}
        </Field>
      </div>

      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">{t("rooms.charges")}</legend>
        <p className="text-sm text-muted-foreground">{t("rooms.chargesHint")}</p>
        {charges.fields.map((row, index) => {
          const rowErrors = errors.charges?.[index];
          const metered = types[index] === "metered";
          return (
            <div key={row.id} className="space-y-4 rounded-md border p-3">
              <div className="grid gap-4 sm:grid-cols-3">
                <Field id={`${id}-charge-${String(index)}-type`} label={t("rooms.chargeType")}>
                  {(control) => (
                    <Select {...control} {...form.register(chargeField(index, "type"))}>
                      {CHARGE_TYPES.map((value) => (
                        <option key={value} value={value}>
                          {t(`chargeType.${value}`)}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
                <Field id={`${id}-charge-${String(index)}-kind`} label={t("rooms.chargeKind")}>
                  {(control) => (
                    <Select {...control} {...form.register(chargeField(index, "kind"))}>
                      {CHARGE_KINDS.map((value) => (
                        <option key={value} value={value}>
                          {t(`chargeKind.${value}`)}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
                <Field
                  id={`${id}-charge-${String(index)}-label`}
                  label={t("rooms.chargeLabel")}
                  error={rowErrors?.label?.message}
                >
                  {(control) => (
                    <Input
                      {...control}
                      autoComplete="off"
                      {...form.register(chargeField(index, "label"))}
                    />
                  )}
                </Field>
                {metered ? (
                  <>
                    <Field
                      id={`${id}-charge-${String(index)}-rate`}
                      label={t("rooms.rate")}
                      error={rowErrors?.rate?.message}
                    >
                      {(control) => (
                        <Input
                          {...control}
                          inputMode="decimal"
                          autoComplete="off"
                          {...form.register(chargeField(index, "rate"))}
                        />
                      )}
                    </Field>
                    <Field
                      id={`${id}-charge-${String(index)}-unit`}
                      label={t("rooms.unit")}
                      error={rowErrors?.unit?.message}
                    >
                      {(control) => (
                        <Input
                          {...control}
                          autoComplete="off"
                          {...form.register(chargeField(index, "unit"))}
                        />
                      )}
                    </Field>
                    <Field
                      id={`${id}-charge-${String(index)}-estimate`}
                      label={t("rooms.estimate")}
                      error={rowErrors?.estimate?.message}
                    >
                      {(control) => (
                        <Input
                          {...control}
                          inputMode="decimal"
                          autoComplete="off"
                          {...form.register(chargeField(index, "estimate"))}
                        />
                      )}
                    </Field>
                  </>
                ) : (
                  <Field
                    id={`${id}-charge-${String(index)}-amount`}
                    label={t("rooms.amount")}
                    error={rowErrors?.amount?.message}
                  >
                    {(control) => (
                      <Input
                        {...control}
                        inputMode="decimal"
                        autoComplete="off"
                        {...form.register(chargeField(index, "amount"))}
                      />
                    )}
                  </Field>
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  charges.remove(index);
                }}
              >
                <Trash aria-hidden />
                {t("rooms.removeCharge")}
              </Button>
            </div>
          );
        })}
        {charges.fields.length < CHARGES_MAX ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              charges.append(NEW_CHARGE);
            }}
          >
            <Plus aria-hidden />
            {t("rooms.addCharge")}
          </Button>
        ) : null}
      </fieldset>

      <FormOutcome failure={failure} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? t("rooms.saving") : t("rooms.saveCategory")}
        </Button>
        <Button type="button" variant="ghost" size="lg" onClick={onDone}>
          {t("rooms.cancel")}
        </Button>
      </div>
    </form>
  );
}
