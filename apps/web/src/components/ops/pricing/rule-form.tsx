"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Checkbox, Choices, Field, FormOutcome, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { percentToBps, wholeNumber } from "@/lib/forms/units";
import { z } from "@/lib/forms/zod";
import { rupeesToPaise } from "@/lib/money";
import { LABEL_MAX, MAX_STAY_MONTHS, TIERS_MAX } from "@/lib/pricing/editor";
import { addRule, replaceRule } from "@/lib/pricing/editor-client";

import { useOpsProblem } from "../problems";
import { useRefresh } from "../use-refresh";
import {
  bodyOf,
  fieldFor,
  isMonthDayInput,
  isPercent,
  isShare,
  isWhole,
  MONTHS,
  NEW_TIER,
  type Rule,
  RULE_KINDS,
  type RuleValues,
  valuesOf,
} from "./rule-values";

const DATE = /^\d{4}-\d{2}-\d{2}$/u;
// How far ahead early-bird and last-minute count: a year, as far as the editor prices.
const MOST_DAYS = 366;
const MONTH_NAME = new Intl.DateTimeFormat("en-IN", { month: "long", timeZone: "UTC" });

type T = ReturnType<typeof useTranslations<"Ops.pricing">>;

function ruleSchema(t: T): z.ZodType<RuleValues, RuleValues> {
  const tier = z.object({ from: z.string(), percent: z.string() });
  return z
    .object({
      kind: z.enum(RULE_KINDS),
      label: z
        .string()
        .trim()
        .min(1, t("form.validation.label", { max: LABEL_MAX }))
        .max(LABEL_MAX, t("form.validation.label", { max: LABEL_MAX })),
      rooms: z.enum(["all", "some"]),
      roomIds: z.array(z.string()),
      enabled: z.boolean(),
      startMonth: z.string(),
      startDay: z.string(),
      endMonth: z.string(),
      endDay: z.string(),
      direction: z.enum(["up", "down"]),
      percent: z.string(),
      days: z.string(),
      maxTaken: z.string(),
      tiers: z.array(tier).max(TIERS_MAX),
      startDate: z.string(),
      endDate: z.string(),
      rent: z.string(),
    })
    .superRefine((values, context) => {
      const flag = (path: (string | number)[], message: string) => {
        context.addIssue({ code: "custom", path, message });
      };
      const percent = () => {
        if (!isPercent(values.percent)) flag(["percent"], t("form.validation.percent"));
      };
      const tiersGoUp = (parse: (text: string) => number | null) => {
        values.tiers.forEach((row, index) => {
          const start = parse(row.from);
          const before = index === 0 ? null : parse(values.tiers[index - 1]?.from ?? "");
          if (start !== null && before !== null && start <= before) {
            flag(["tiers", index, "from"], t("form.validation.tiersUp"));
          }
        });
      };
      if (values.rooms === "some" && values.roomIds.length === 0) {
        flag(["roomIds"], t("form.validation.rooms"));
      }
      switch (values.kind) {
        case "season":
          if (!isMonthDayInput(values.startMonth, values.startDay)) {
            flag(["startDay"], t("form.validation.day"));
          }
          if (!isMonthDayInput(values.endMonth, values.endDay)) {
            flag(["endDay"], t("form.validation.day"));
          }
          percent();
          break;
        case "early_bird":
          if (!isWhole(values.days, 1, MOST_DAYS)) {
            flag(["days"], t("form.validation.days", { min: 1, max: MOST_DAYS }));
          }
          percent();
          break;
        case "last_minute":
          if (!isWhole(values.days, 0, MOST_DAYS)) {
            flag(["days"], t("form.validation.days", { min: 0, max: MOST_DAYS }));
          }
          if (!isShare(values.maxTaken)) flag(["maxTaken"], t("form.validation.share"));
          percent();
          break;
        case "occupancy":
          values.tiers.forEach((row, index) => {
            if (!isPercent(row.from)) flag(["tiers", index, "from"], t("form.validation.percent"));
            if (!isPercent(row.percent)) {
              flag(["tiers", index, "percent"], t("form.validation.percent"));
            }
          });
          tiersGoUp(percentToBps);
          break;
        case "length_of_stay":
          values.tiers.forEach((row, index) => {
            if (!isWhole(row.from, 2, MAX_STAY_MONTHS)) {
              flag(["tiers", index, "from"], t("form.validation.months", { max: MAX_STAY_MONTHS }));
            }
            if (!isPercent(row.percent)) {
              flag(["tiers", index, "percent"], t("form.validation.percent"));
            }
          });
          tiersGoUp(wholeNumber);
          break;
        case "override":
          if (!DATE.test(values.startDate)) flag(["startDate"], t("form.validation.date"));
          if (!DATE.test(values.endDate)) {
            flag(["endDate"], t("form.validation.date"));
          } else if (DATE.test(values.startDate) && values.endDate < values.startDate) {
            flag(["endDate"], t("form.validation.dateOrder"));
          }
          if ((rupeesToPaise(values.rent) ?? 0) <= 0) flag(["rent"], t("form.validation.amount"));
          break;
      }
    });
}

/** A tier row's field, as React Hook Form names it. */
function tierField(index: number, key: "from" | "percent"): `tiers.${number}.${typeof key}` {
  return `tiers.${index.toString()}.${key}` as `tiers.${number}.${typeof key}`;
}

/**
 * A pricing rule of a draft (step 4.6, ADR 0041): new, or `rule` to change. Each kind asks only
 * what it needs; the API checks the rule again, and the draft's problems say what would stop it
 * going into force.
 */
export function RuleForm({
  ruleSetId,
  rule,
  rooms,
  onDone,
}: {
  ruleSetId: string;
  rule?: Rule;
  rooms: readonly { id: string; label: string }[];
  onDone: () => void;
}) {
  const t = useTranslations("Ops.pricing");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const form = useForm<RuleValues>({
    resolver: zodResolver(ruleSchema(t)),
    defaultValues: valuesOf(rule),
  });
  const tiers = useFieldArray({ control: form.control, name: "tiers" });
  const [kind, roomsMode, roomIds] = useWatch({
    control: form.control,
    name: ["kind", "rooms", "roomIds"],
  });
  const { errors, isSubmitting, isSubmitted } = form.formState;

  async function save(values: RuleValues) {
    setFailure(null);
    try {
      const body = bodyOf(values);
      if (rule === undefined) await addRule(ruleSetId, body);
      else await replaceRule(rule.id, body);
      refresh();
      onDone();
    } catch (error) {
      const shown = showFieldErrors(error, form.setError, fieldFor);
      if (!shown) setFailure(problem(error));
    }
  }

  const months = MONTHS.map((month) => ({
    value: month,
    label: MONTH_NAME.format(Date.UTC(2000, Number(month) - 1, 1)),
  }));
  const monthDay = (which: "start" | "end") => {
    const monthName = which === "start" ? "startMonth" : "endMonth";
    const dayName = which === "start" ? "startDay" : "endDay";
    return (
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">
          {t(which === "start" ? "form.seasonStart" : "form.seasonEnd")}
        </legend>
        <div className="grid grid-cols-[2fr_1fr] gap-3">
          <Field id={`${id}-${monthName}`} label={t("form.month")}>
            {(control) => (
              <Select {...control} {...form.register(monthName)}>
                <option value="">{t("form.month")}</option>
                {months.map((month) => (
                  <option key={month.value} value={month.value}>
                    {month.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field id={`${id}-${dayName}`} label={t("form.day")} error={errors[dayName]?.message}>
            {(control) => <Input {...control} inputMode="numeric" {...form.register(dayName)} />}
          </Field>
        </div>
      </fieldset>
    );
  };
  const percentField = (label: string) => (
    <Field id={`${id}-percent`} label={label} error={errors.percent?.message}>
      {(control) => <Input {...control} inputMode="decimal" {...form.register("percent")} />}
    </Field>
  );

  return (
    <form
      noValidate
      aria-label={
        rule === undefined ? t("form.addTitle") : t("form.editTitle", { label: rule.label })
      }
      className="space-y-5 rounded-lg border p-4"
      onSubmit={(event) => {
        void form.handleSubmit(save)(event);
      }}
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <Field id={`${id}-kind`} label={t("form.kind")} hint={t(`form.kindHints.${kind}`)}>
          {(control) => (
            <Select {...control} {...form.register("kind")}>
              {RULE_KINDS.map((option) => (
                <option key={option} value={option}>
                  {t(`rules.kinds.${option}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field
          id={`${id}-label`}
          label={t("form.label")}
          hint={t("form.labelHint", { max: LABEL_MAX })}
          error={errors.label?.message}
        >
          {(control) => <Input {...control} maxLength={LABEL_MAX} {...form.register("label")} />}
        </Field>
      </div>

      {kind === "season" ? (
        <div className="grid gap-5 sm:grid-cols-2">
          {monthDay("start")}
          {monthDay("end")}
          <Choices
            id={`${id}-direction`}
            legend={t("form.direction")}
            options={[
              { value: "up", label: t("form.up") },
              { value: "down", label: t("form.down") },
            ]}
            registration={form.register("direction")}
          />
          {percentField(t("form.change"))}
        </div>
      ) : null}

      {kind === "early_bird" || kind === "last_minute" ? (
        <div className="grid gap-5 sm:grid-cols-3">
          <Field
            id={`${id}-days`}
            label={t(kind === "early_bird" ? "form.minDays" : "form.maxDays")}
            error={errors.days?.message}
          >
            {(control) => <Input {...control} inputMode="numeric" {...form.register("days")} />}
          </Field>
          {kind === "last_minute" ? (
            <Field id={`${id}-taken`} label={t("form.maxTaken")} error={errors.maxTaken?.message}>
              {(control) => (
                <Input {...control} inputMode="decimal" {...form.register("maxTaken")} />
              )}
            </Field>
          ) : null}
          {percentField(t("form.discount"))}
        </div>
      ) : null}

      {kind === "occupancy" || kind === "length_of_stay" ? (
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">{t("form.tiers")}</legend>
          {tiers.fields.map((row, index) => (
            <fieldset key={row.id} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]">
              <legend className="sr-only">{t("form.tier", { number: index + 1 })}</legend>
              <Field
                id={`${id}-tier-${String(index)}-from`}
                label={t(kind === "occupancy" ? "form.fromTaken" : "form.fromMonths")}
                error={errors.tiers?.[index]?.from?.message}
              >
                {(control) => (
                  <Input
                    {...control}
                    inputMode={kind === "occupancy" ? "decimal" : "numeric"}
                    {...form.register(tierField(index, "from"))}
                  />
                )}
              </Field>
              <Field
                id={`${id}-tier-${String(index)}-percent`}
                label={t(kind === "occupancy" ? "form.premium" : "form.discount")}
                error={errors.tiers?.[index]?.percent?.message}
              >
                {(control) => (
                  <Input
                    {...control}
                    inputMode="decimal"
                    {...form.register(tierField(index, "percent"))}
                  />
                )}
              </Field>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="size-11"
                disabled={tiers.fields.length === 1}
                aria-label={t("form.removeTier", { number: index + 1 })}
                onClick={() => {
                  tiers.remove(index);
                }}
              >
                <Trash aria-hidden="true" />
              </Button>
            </fieldset>
          ))}
          <Button
            type="button"
            variant="outline"
            disabled={tiers.fields.length >= TIERS_MAX}
            onClick={() => {
              tiers.append({ ...NEW_TIER });
            }}
          >
            <Plus aria-hidden="true" />
            {t("form.addTier")}
          </Button>
        </fieldset>
      ) : null}

      {kind === "override" ? (
        <div className="grid gap-5 sm:grid-cols-3">
          <Field id={`${id}-start`} label={t("form.startDate")} error={errors.startDate?.message}>
            {(control) => <Input {...control} type="date" {...form.register("startDate")} />}
          </Field>
          <Field id={`${id}-end`} label={t("form.endDate")} error={errors.endDate?.message}>
            {(control) => <Input {...control} type="date" {...form.register("endDate")} />}
          </Field>
          <Field id={`${id}-rent`} label={t("form.rent")} error={errors.rent?.message}>
            {(control) => <Input {...control} inputMode="decimal" {...form.register("rent")} />}
          </Field>
        </div>
      ) : null}

      <div className="space-y-3">
        <Choices
          id={`${id}-rooms`}
          legend={t("form.rooms")}
          options={[
            { value: "all", label: t("form.allRooms") },
            { value: "some", label: t("form.someRooms") },
          ]}
          registration={form.register("rooms")}
        />
        {roomsMode === "some" ? (
          <fieldset aria-describedby={errors.roomIds ? `${id}-rooms-error` : undefined}>
            <legend className="sr-only">{t("form.someRooms")}</legend>
            {rooms.map((room) => (
              <Checkbox
                key={room.id}
                label={room.label}
                checked={roomIds.includes(room.id)}
                onChange={(event) => {
                  const next = event.currentTarget.checked
                    ? [...roomIds, room.id]
                    : roomIds.filter((chosen) => chosen !== room.id);
                  form.setValue("roomIds", next, { shouldValidate: isSubmitted });
                }}
              />
            ))}
            {errors.roomIds?.message ? (
              <p id={`${id}-rooms-error`} className="text-sm text-destructive">
                {errors.roomIds.message}
              </p>
            ) : null}
          </fieldset>
        ) : null}
        <div>
          <Checkbox
            label={t("form.enabled")}
            aria-describedby={`${id}-enabled-hint`}
            {...form.register("enabled")}
          />
          <p id={`${id}-enabled-hint`} className="text-sm text-muted-foreground">
            {t("form.enabledHint")}
          </p>
        </div>
      </div>

      <FormOutcome failure={failure} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? t("form.saving") : t("form.save")}
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>
          {t("form.cancel")}
        </Button>
      </div>
    </form>
  );
}
