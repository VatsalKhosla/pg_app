"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMessages, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { useRefresh } from "@/components/ops/use-refresh";
import { Button } from "@/components/ui/button";
import { Field, FormOutcome, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import {
  changeBookingPolicy,
  changeFeePolicy,
  changePricingCaps,
  type BookingPolicyInput,
  type FeePolicyInput,
  type PricingCapsInput,
} from "@/lib/admin/client";
import { percentToBps, wholeNumber } from "@/lib/admin/units";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";
import { rupeesToPaise } from "@/lib/money";

/** How a policy's field is typed: a percentage, rupees, a whole number, or one of a few. */
export type PolicyFieldKind = "percent" | "rupees" | "whole" | "choice";

export interface PolicyField {
  /** The API's name for it, e.g. "tokenPaise". */
  name: string;
  label: string;
  hint?: string;
  kind: PolicyFieldKind;
  choices?: readonly { value: string; label: string }[];
}

export type PolicyName = "fee" | "booking" | "caps";

const NOTE_MAX = 500;
// The codes whose message the API completes with what it found (every problem, in English).
const WITH_DETAIL: readonly string[] = ["POLICY_INVALID"];

const SEND = {
  fee: (body: Record<string, unknown>) => changeFeePolicy(body as FeePolicyInput),
  booking: (body: Record<string, unknown>) => changeBookingPolicy(body as BookingPolicyInput),
  caps: (body: Record<string, unknown>) => changePricingCaps(body as PricingCapsInput),
} as const;

function parsed(kind: PolicyFieldKind, text: string): number | string | null {
  switch (kind) {
    case "percent":
      return percentToBps(text);
    case "rupees":
      return rupeesToPaise(text);
    case "whole":
      return wholeNumber(text);
    case "choice":
      return text === "" ? null : text;
  }
}

/**
 * One policy's next version (step 4.1, ADR 0036), from the one in force: rates as percentages,
 * amounts in rupees, terms in whole numbers. The API checks it against the founders' rules and
 * says what's wrong; from the moment it's applied, new quotes use it.
 */
export function PolicyForm({
  policy,
  fields,
  initial,
}: {
  policy: PolicyName;
  fields: readonly PolicyField[];
  initial: Readonly<Record<string, string>>;
}) {
  const t = useTranslations("Admin");
  const messages: Record<string, string> = useMessages().Admin.errors;
  const id = useId();
  const refresh = useRefresh();
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState("");

  const messageFor: Record<PolicyFieldKind, string> = {
    percent: t("validation.percent"),
    rupees: t("validation.amount"),
    whole: t("validation.whole"),
    choice: t("validation.choose"),
  };
  // One string field each, as typed; converted when sent.
  const shape: Record<string, z.ZodType<string, string>> = {
    note: z.string().trim().max(NOTE_MAX, t("validation.tooLong")),
  };
  for (const field of fields) {
    shape[field.name] = z
      .string()
      .refine((text) => parsed(field.kind, text) !== null, messageFor[field.kind]);
  }
  const schema = z.object(shape);
  type Values = Record<string, string>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { ...initial, note: "" },
  });
  const { errors, isSubmitting } = form.formState;

  async function send(values: Values) {
    setFailure(null);
    setSaved("");
    const body: Record<string, unknown> = { note: values.note?.trim() ?? "" };
    for (const field of fields) body[field.name] = parsed(field.kind, values[field.name] ?? "");
    try {
      await SEND[policy](body);
      form.reset({ ...values, note: "" });
      setSaved(t("policies.saved"));
      refresh();
    } catch (error) {
      const names = new Set(fields.map((field) => field.name));
      const shown = showFieldErrors(error, form.setError, (pointer) => {
        const name = pointer.slice(1);
        return names.has(name) ? name : undefined;
      });
      if (!shown) setFailure(problemMessage(error, messages, WITH_DETAIL));
    }
  }

  return (
    <form
      noValidate
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(send)(event);
      }}
    >
      <div className="grid gap-5 sm:grid-cols-2">
        {fields.map((field) => (
          <Field
            key={field.name}
            id={`${id}-${field.name}`}
            label={field.label}
            {...(field.hint === undefined ? {} : { hint: field.hint })}
            error={errors[field.name]?.message}
          >
            {(control) =>
              field.kind === "choice" ? (
                <Select {...control} {...form.register(field.name)}>
                  {(field.choices ?? []).map((choice) => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
                    </option>
                  ))}
                </Select>
              ) : (
                <Input
                  {...control}
                  inputMode={field.kind === "whole" ? "numeric" : "decimal"}
                  autoComplete="off"
                  {...form.register(field.name)}
                />
              )
            }
          </Field>
        ))}
      </div>
      <Field id={`${id}-note`} label={t("policies.note")} error={errors.note?.message}>
        {(control) => <Input {...control} maxLength={NOTE_MAX} {...form.register("note")} />}
      </Field>
      <FormOutcome failure={failure} saved={saved} />
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? t("policies.saving") : t("policies.save")}
      </Button>
    </form>
  );
}
