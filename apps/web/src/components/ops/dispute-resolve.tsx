"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { Choices, Field, FormOutcome, Textarea } from "@/components/ui/fields";
import { ApiError } from "@/lib/api/errors";
import { type Outcome, resolveDispute } from "@/lib/disputes/client";
import { z } from "@/lib/forms/zod";

const OUTCOMES = ["refund", "uphold"] as const satisfies readonly Outcome[];
// The API's limit (ADR 0051).
const NOTES_MAX = 1_000;

/**
 * Settling a student's report (step 5.7, ADR 0051): refund it (the bed released and the token
 * refunded in full) or uphold it (the stay goes ahead), with a note for the record. Both text
 * the student and the owner, and neither can be undone, so ops confirm what they chose first.
 */
export function DisputeResolve({ id, code }: { id: string; code: string }) {
  const t = useTranslations("Ops.disputes");
  const formId = useId();
  const router = useRouter();
  const schema = z.object({
    outcome: z.enum(OUTCOMES, { error: t("chooseOutcome") }),
    notes: z.string().trim().min(1, t("needNotes")).max(NOTES_MAX, t("needNotes")),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { notes: "" } });
  const { errors } = form.formState;
  const [chosen, setChosen] = useState<Values | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function settle({ outcome, notes }: Values) {
    setBusy(true);
    setFailure(null);
    try {
      await resolveDispute(id, outcome, notes);
      setChosen(null);
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError && error.code === "INVALID_TRANSITION") {
        setChosen(null);
        setFailure(t("settledAlready"));
        router.refresh();
        return;
      }
      setFailure(problemMessage(error, { generic: t("failed") }));
    } finally {
      setBusy(false);
    }
  }

  if (chosen !== null) {
    return (
      <section aria-labelledby={`${formId}-confirm`} className="space-y-3 rounded-lg border p-4">
        <h2 id={`${formId}-confirm`} className="font-semibold">
          {t(`confirm.${chosen.outcome}.title`, { code })}
        </h2>
        <p>{t(`confirm.${chosen.outcome}.body`)}</p>
        <div className="flex flex-wrap gap-3">
          <Button
            variant={chosen.outcome === "refund" ? "destructive" : "default"}
            disabled={busy}
            onClick={() => {
              void settle(chosen);
            }}
          >
            {busy ? t("saving") : t(`confirm.${chosen.outcome}.yes`)}
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => {
              setChosen(null);
            }}
          >
            {t("change")}
          </Button>
        </div>
        <FormOutcome failure={failure} />
      </section>
    );
  }
  return (
    <form
      noValidate
      aria-labelledby={`${formId}-title`}
      className="space-y-4"
      onSubmit={(event) => {
        void form.handleSubmit((values) => {
          setFailure(null);
          setChosen(values);
        })(event);
      }}
    >
      <h2 id={`${formId}-title`} className="text-lg font-semibold">
        {t("settleTitle")}
      </h2>
      <Choices
        id={`${formId}-outcome`}
        legend={t("outcome")}
        options={OUTCOMES.map((outcome) => ({ value: outcome, label: t(`outcomes.${outcome}`) }))}
        registration={form.register("outcome")}
        error={errors.outcome?.message}
      />
      <Field
        id={`${formId}-notes`}
        label={t("notes")}
        hint={t("notesHint")}
        error={errors.notes?.message}
      >
        {(control) => (
          <Textarea {...control} rows={3} maxLength={NOTES_MAX} {...form.register("notes")} />
        )}
      </Field>
      <FormOutcome failure={failure} />
      <Button type="submit">{t("next")}</Button>
    </form>
  );
}
