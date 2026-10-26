"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { z } from "@/lib/forms/zod";
import { cancelVisit } from "@/lib/ops/client";

import { Field, FormOutcome, Textarea } from "./fields";
import { useOpsProblem } from "./problems";
import { useRefresh } from "./use-refresh";

const REASON_MAX = 500;

/** Call off a booked visit, saying why; the listing's verification status goes back. */
export function CancelVisit({ visitId }: { visitId: string }) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    reason: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .max(REASON_MAX, t("validation.tooLong")),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { reason: "" },
  });

  async function cancel({ reason }: { reason: string }) {
    setFailure(null);
    try {
      await cancelVisit(visitId, reason);
      refresh();
    } catch (error) {
      setFailure(problem(error));
    }
  }

  if (!open) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          setOpen(true);
        }}
      >
        {t("visits.cancel")}
      </Button>
    );
  }
  return (
    <form
      noValidate
      className="space-y-3"
      onSubmit={(event) => {
        void form.handleSubmit(cancel)(event);
      }}
    >
      <Field
        id={`${id}-reason`}
        label={t("visits.cancelReason")}
        error={form.formState.errors.reason?.message}
      >
        {(control) => <Textarea {...control} rows={2} {...form.register("reason")} />}
      </Field>
      <FormOutcome failure={failure} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" size="sm" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? t("visits.cancelling") : t("visits.cancelConfirm")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setOpen(false);
          }}
        >
          {t("visits.keep")}
        </Button>
      </div>
    </form>
  );
}
