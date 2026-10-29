"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { Field, Textarea } from "@/components/ui/fields";
import { z } from "@/lib/forms/zod";
import { acknowledgeGrievance, resolveGrievance } from "@/lib/grievances/client";

export interface GrievanceFormsText {
  replyTitle: string;
  replyHint: string;
  acknowledge: string;
  resolutionTitle: string;
  resolutionHint: string;
  resolve: string;
  saving: string;
  needText: string;
  errors: Record<string, string>;
}

// The API's limit for both (ADR 0034).
const MAX_LENGTH = 2_000;

/** One text the complainant will read, sent with one button: a reply, or a resolution. */
function TextForm({
  label,
  hint,
  submit,
  text,
  onSend,
}: {
  label: string;
  hint: string;
  submit: string;
  text: GrievanceFormsText;
  onSend: (value: string) => Promise<unknown>;
}) {
  const id = useId();
  const router = useRouter();
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    value: z.string().trim().min(1, text.needText).max(MAX_LENGTH, text.needText),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { value: "" } });
  const { errors, isSubmitting } = form.formState;

  async function send({ value }: Values) {
    setFailure(null);
    try {
      await onSend(value);
      form.reset();
      router.refresh();
    } catch (error) {
      setFailure(problemMessage(error, text.errors));
    }
  }

  return (
    <form
      noValidate
      className="space-y-3"
      onSubmit={(event) => {
        void form.handleSubmit(send)(event);
      }}
    >
      <Field id={`${id}-value`} label={label} hint={hint} error={errors.value?.message}>
        {(control) => (
          <Textarea {...control} rows={4} maxLength={MAX_LENGTH} {...form.register("value")} />
        )}
      </Field>
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? text.saving : submit}
      </Button>
    </form>
  );
}

/**
 * The grievance officer's two steps (step 3.8, ADR 0034): acknowledge with a reply, then resolve
 * with what was done; resolving at once acknowledges too. Each is audited, and the person sees it.
 */
export function GrievanceForms({
  ticket,
  next,
  text,
}: {
  ticket: string;
  next: readonly string[];
  text: GrievanceFormsText;
}) {
  return (
    <div className="space-y-8">
      {next.includes("acknowledged") ? (
        <TextForm
          label={text.replyTitle}
          hint={text.replyHint}
          submit={text.acknowledge}
          text={text}
          onSend={(reply) => acknowledgeGrievance(ticket, reply)}
        />
      ) : null}
      {next.includes("resolved") ? (
        <TextForm
          label={text.resolutionTitle}
          hint={text.resolutionHint}
          submit={text.resolve}
          text={text}
          onSend={(resolution) => resolveGrievance(ticket, resolution)}
        />
      ) : null}
    </div>
  );
}
