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
import { endRentBand, type RentBandInput, setRentBand } from "@/lib/admin/client";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";
import { rupeesToPaise } from "@/lib/money";

const OCCUPANCIES = ["single", "double", "triple", "quad"] as const;
const SOURCES = ["internal", "official"] as const;
const REFERENCE_MAX = 300;
const NOTE_MAX = 500;
const WITH_DETAIL: readonly string[] = ["POLICY_INVALID"];

type FieldName = "locality" | "occupancy" | "minRent" | "maxRent" | "source" | "reference";
const POINTERS: Record<string, FieldName> = {
  "/locality": "locality",
  "/occupancy": "occupancy",
  "/minRentPaise": "minRent",
  "/maxRentPaise": "maxRent",
  "/source": "source",
  "/reference": "reference",
};

/**
 * A rent band for one locality and occupancy, in force from now (step 4.1, ADR 0036); the one in
 * force before it ends. The API checks the rents and an official band's reference.
 */
export function RentBandForm({
  localities,
}: {
  localities: readonly { slug: string; name: string }[];
}) {
  const t = useTranslations("Admin");
  const messages: Record<string, string> = useMessages().Admin.errors;
  const id = useId();
  const refresh = useRefresh();
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  const amount = z.string().refine((text) => rupeesToPaise(text) !== null, t("validation.amount"));
  const schema = z.object({
    locality: z.string().min(1, t("validation.choose")),
    occupancy: z.string().min(1, t("validation.choose")),
    minRent: amount,
    maxRent: amount,
    source: z.enum(SOURCES),
    reference: z.string().trim().max(REFERENCE_MAX, t("validation.tooLong")),
    note: z.string().trim().max(NOTE_MAX, t("validation.tooLong")),
  });
  type Values = z.infer<typeof schema>;
  const empty: Values = {
    locality: "",
    occupancy: "",
    minRent: "",
    maxRent: "",
    source: "internal",
    reference: "",
    note: "",
  };
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: empty });
  const { errors, isSubmitting } = form.formState;

  async function send(values: Values) {
    setFailure(null);
    setSaved("");
    const body: RentBandInput = {
      locality: values.locality,
      occupancy: values.occupancy as RentBandInput["occupancy"],
      minRentPaise: rupeesToPaise(values.minRent) ?? 0,
      maxRentPaise: rupeesToPaise(values.maxRent) ?? 0,
      source: values.source,
      reference: values.reference,
      note: values.note,
    };
    try {
      await setRentBand(body);
      form.reset(empty);
      setSaved(t("bands.saved"));
      refresh();
    } catch (error) {
      const shown = showFieldErrors(error, form.setError, (pointer) => POINTERS[pointer]);
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
        <Field id={`${id}-locality`} label={t("bands.locality")} error={errors.locality?.message}>
          {(control) => (
            <Select {...control} {...form.register("locality")}>
              <option value="">{t("bands.chooseLocality")}</option>
              {localities.map((place) => (
                <option key={place.slug} value={place.slug}>
                  {place.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field
          id={`${id}-occupancy`}
          label={t("bands.occupancy")}
          error={errors.occupancy?.message}
        >
          {(control) => (
            <Select {...control} {...form.register("occupancy")}>
              <option value="">{t("bands.chooseOccupancy")}</option>
              {OCCUPANCIES.map((occupancy) => (
                <option key={occupancy} value={occupancy}>
                  {t(`bands.occupancies.${occupancy}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field id={`${id}-min`} label={t("bands.min")} error={errors.minRent?.message}>
          {(control) => <Input {...control} inputMode="decimal" {...form.register("minRent")} />}
        </Field>
        <Field id={`${id}-max`} label={t("bands.max")} error={errors.maxRent?.message}>
          {(control) => <Input {...control} inputMode="decimal" {...form.register("maxRent")} />}
        </Field>
        <Field id={`${id}-source`} label={t("bands.source")} error={errors.source?.message}>
          {(control) => (
            <Select {...control} {...form.register("source")}>
              {SOURCES.map((source) => (
                <option key={source} value={source}>
                  {t(`bands.sources.${source}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field
          id={`${id}-reference`}
          label={t("bands.reference")}
          hint={t("bands.referenceHint")}
          error={errors.reference?.message}
        >
          {(control) => (
            <Input {...control} maxLength={REFERENCE_MAX} {...form.register("reference")} />
          )}
        </Field>
      </div>
      <Field id={`${id}-note`} label={t("bands.note")} error={errors.note?.message}>
        {(control) => <Input {...control} maxLength={NOTE_MAX} {...form.register("note")} />}
      </Field>
      <FormOutcome failure={failure} saved={saved} />
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? t("bands.saving") : t("bands.save")}
      </Button>
    </form>
  );
}

/** Ends a band in force: from now, its locality and occupancy have none. */
export function EndBandButton({ id, label }: { id: string; label: string }) {
  const t = useTranslations("Admin");
  const messages: Record<string, string> = useMessages().Admin.errors;
  const refresh = useRefresh();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function end() {
    setBusy(true);
    setFailure(null);
    try {
      await endRentBand(id);
      refresh();
    } catch (error) {
      setFailure(problemMessage(error, messages, WITH_DETAIL));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        aria-label={`${t("bands.end")}: ${label}`}
        onClick={() => {
          void end();
        }}
      >
        {busy ? t("bands.ending") : t("bands.end")}
      </Button>
      <FormOutcome failure={failure} />
    </div>
  );
}
