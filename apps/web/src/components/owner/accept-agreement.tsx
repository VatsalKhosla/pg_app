"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { OWNER_AGREEMENT_PATH, OWNER_HOME_PATH } from "@/lib/auth/routes";
import { z } from "@/lib/forms/zod";
import { acceptAgreement } from "@/lib/owner/client";

export interface AcceptText {
  agree: string;
  required: string;
  submit: string;
  submitting: string;
  /** Error messages by the API's code, with the general one as `generic`. */
  errors: Record<string, string>;
}

/**
 * Click-wrap acceptance (ADR 0025): the owner ticks the box themselves, since nothing is ticked
 * for them, and accepts exactly the version and text they were shown. If the agreement changed
 * while they read it, the API refuses (AGREEMENT_CHANGED) and the page reloads with the new text.
 */
export function AcceptAgreement({
  version,
  documentSha256,
  text,
}: {
  version: string;
  documentSha256: string;
  text: AcceptText;
}) {
  const id = useId();
  const router = useRouter();
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    agreed: z.boolean().refine((agreed) => agreed, { message: text.required }),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { agreed: false } });
  const { errors, isSubmitting } = form.formState;

  async function accept() {
    setFailure(null);
    try {
      await acceptAgreement({ version, documentSha256 });
      router.push(OWNER_HOME_PATH);
    } catch (error) {
      if (error instanceof ApiError && error.code === "AGREEMENT_CHANGED") {
        router.replace(`${OWNER_AGREEMENT_PATH}?changed=1` as Route);
        return;
      }
      setFailure(problemMessage(error, text.errors));
    }
  }

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) => {
        void form.handleSubmit(accept)(event);
      }}
    >
      <div className="space-y-2">
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-5 shrink-0 accent-primary"
            aria-invalid={errors.agreed !== undefined}
            aria-describedby={errors.agreed ? `${id}-error` : undefined}
            {...form.register("agreed")}
          />
          <span>{text.agree}</span>
        </label>
        {errors.agreed?.message === undefined ? null : (
          <p id={`${id}-error`} className="text-sm text-destructive">
            {errors.agreed.message}
          </p>
        )}
      </div>
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
      <Button type="submit" size="lg" disabled={isSubmitting}>
        {isSubmitting ? text.submitting : text.submit}
      </Button>
    </form>
  );
}
