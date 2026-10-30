"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Choices, Field, FormOutcome, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";
import { placeBlock } from "@/lib/inventory/client";

import { useOpsProblem } from "../problems";
import { useRefresh } from "../use-refresh";

const DATE = /^\d{4}-\d{2}-\d{2}$/u;
const NOTE_MAX = 300;
const KINDS = ["offline_tenant", "maintenance"] as const;

type FieldName = "start" | "end" | "note";
const POINTERS: Record<string, FieldName> = { "/start": "start", "/end": "end", "/note": "note" };

/**
 * Holds a bed for an offline tenant or maintenance (step 5.1, ADR 0044), from a day and until
 * one, or until further notice. The API refuses a bed something already holds then, and says
 * what does.
 */
export function BlockForm({
  beds,
  today,
}: {
  beds: readonly { id: string; label: string }[];
  /** Today in India, YYYY-MM-DD. */
  today: string;
}) {
  const t = useTranslations("Ops.beds");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  const schema = z
    .object({
      bed: z.string().min(1, t("add.validation.bed")),
      kind: z.enum(KINDS),
      start: z.string().regex(DATE, t("add.validation.date")),
      end: z.string(),
      note: z.string().trim().max(NOTE_MAX),
    })
    .refine((values) => values.end === "" || (DATE.test(values.end) && values.end > values.start), {
      message: t("add.validation.order"),
      path: ["end"],
    });
  type Values = z.infer<typeof schema>;
  const empty: Values = { bed: "", kind: "offline_tenant", start: today, end: "", note: "" };
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: empty });
  const { errors, isSubmitting } = form.formState;

  async function hold(values: Values) {
    setFailure(null);
    setSaved("");
    try {
      await placeBlock(values.bed, {
        kind: values.kind,
        start: values.start,
        end: values.end === "" ? null : values.end,
        note: values.note,
      });
      form.reset({ ...empty, kind: values.kind });
      setSaved(t("add.saved"));
      refresh();
    } catch (error) {
      const shown = showFieldErrors(error, form.setError, (pointer) => POINTERS[pointer]);
      if (!shown) setFailure(problem(error));
    }
  }

  return (
    <form
      noValidate
      aria-label={t("add.title")}
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(hold)(event);
      }}
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <Field id={`${id}-bed`} label={t("add.bed")} error={errors.bed?.message}>
          {(control) => (
            <Select {...control} {...form.register("bed")}>
              <option value="">{t("add.chooseBed")}</option>
              {beds.map((bed) => (
                <option key={bed.id} value={bed.id}>
                  {bed.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Choices
          id={`${id}-kind`}
          legend={t("add.kind")}
          options={KINDS.map((kind) => ({ value: kind, label: t(`kinds.${kind}`) }))}
          registration={form.register("kind")}
        />
        <Field id={`${id}-start`} label={t("add.start")} error={errors.start?.message}>
          {(control) => <Input {...control} type="date" {...form.register("start")} />}
        </Field>
        <Field
          id={`${id}-end`}
          label={t("add.end")}
          hint={t("add.endHint")}
          error={errors.end?.message}
        >
          {(control) => <Input {...control} type="date" {...form.register("end")} />}
        </Field>
      </div>
      <Field id={`${id}-note`} label={t("add.note")} error={errors.note?.message}>
        {(control) => <Input {...control} maxLength={NOTE_MAX} {...form.register("note")} />}
      </Field>
      <FormOutcome failure={failure} saved={saved} />
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? t("add.saving") : t("add.save")}
      </Button>
    </form>
  );
}
