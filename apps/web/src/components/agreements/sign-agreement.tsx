"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { PenLine, Send } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { Field, FormOutcome } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import {
  askForSigningCode,
  type Side,
  type SigningCodeSent,
  signAgreement,
} from "@/lib/agreements/client";
import { ApiError } from "@/lib/api/errors";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";

export interface SignAgreementText {
  title: string;
  intro: string;
  getCode: string;
  sending: string;
  sent: string;
  resend: string;
  /** "Development code: {code}", with the code put in by the component. */
  developmentCode: string;
  code: string;
  needCode: string;
  fullName: string;
  fullNameHint: string;
  needName: string;
  agree: string;
  signing: string;
  errors: Record<string, string>;
}

// The API's rules (ADR 0070): six digits; a name of 2 to 80 letters, spaces, dots, apostrophes
// and hyphens.
const CODE = /^\d{6}$/u;
const NAME = /^[\p{L}\p{M}][\p{L}\p{M} .'’-]*$/u;

/**
 * Signing a booking's rent agreement (ADR 0070): ask for a one-time code, then sign with it and
 * the signer's full name, for exactly the text on the page (its SHA-256). If the text changed in
 * the meantime the API refuses, and the page shows the new text to read again.
 */
export function SignAgreement({
  side,
  code,
  textSha256,
  text,
}: {
  side: Side;
  code: string;
  textSha256: string;
  text: SignAgreementText;
}) {
  const id = useId();
  const router = useRouter();
  const [sent, setSent] = useState<SigningCodeSent | null>(null);
  const [asking, setAsking] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    code: z.string().trim().regex(CODE, text.needCode),
    fullName: z
      .string()
      .trim()
      .min(2, text.needName)
      .max(80, text.needName)
      .regex(NAME, text.needName),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { code: "", fullName: "" },
  });
  const { errors, isSubmitting } = form.formState;

  async function ask() {
    setAsking(true);
    setFailure(null);
    try {
      setSent(await askForSigningCode(side, code));
    } catch (error) {
      setFailure(problemMessage(error, text.errors));
      if (error instanceof ApiError && error.code === "INVALID_TRANSITION") router.refresh();
    } finally {
      setAsking(false);
    }
  }

  async function sign(values: Values) {
    setFailure(null);
    try {
      await signAgreement(side, code, { ...values, textSha256 });
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError && error.code.startsWith("SIGNING_CODE_")) {
        form.setError("code", {
          message: problemMessage(error, text.errors, ["SIGNING_CODE_INVALID"]),
        });
        return;
      }
      if (
        showFieldErrors(error, form.setError, (pointer) =>
          pointer === "/fullName" ? "fullName" : pointer === "/code" ? "code" : undefined,
        )
      ) {
        return;
      }
      setFailure(problemMessage(error, text.errors));
      if (
        error instanceof ApiError &&
        ["AGREEMENT_TEXT_CHANGED", "INVALID_TRANSITION"].includes(error.code)
      ) {
        router.refresh();
      }
    }
  }

  return (
    <div
      data-print-hidden
      className="space-y-4 rounded-2xl border border-primary/30 bg-primary-soft/50 p-5"
    >
      <div className="space-y-1.5">
        <h3 id={`${id}-title`} className="font-semibold text-foreground">
          {text.title}
        </h3>
        <p className="text-sm text-muted-foreground">{text.intro}</p>
      </div>
      {sent === null ? (
        <Button type="button" disabled={asking} onClick={() => void ask()}>
          <Send aria-hidden />
          {asking ? text.sending : text.getCode}
        </Button>
      ) : (
        <form
          method="post"
          noValidate
          aria-labelledby={`${id}-title`}
          className="space-y-4"
          onSubmit={(event) => {
            void form.handleSubmit(sign)(event);
          }}
        >
          <p role="status" className="text-sm font-medium text-foreground">
            {text.sent}
          </p>
          {sent.developmentCode === null || sent.developmentCode === undefined ? null : (
            <p className="rounded-lg bg-warning-soft px-3 py-2 font-mono text-sm text-warning-soft-foreground">
              {text.developmentCode.replace("{code}", sent.developmentCode)}
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id={`${id}-code`} label={text.code} error={errors.code?.message}>
              {(control) => (
                <Input
                  {...control}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  {...form.register("code")}
                />
              )}
            </Field>
            <Field
              id={`${id}-name`}
              label={text.fullName}
              hint={text.fullNameHint}
              error={errors.fullName?.message}
            >
              {(control) => (
                <Input
                  {...control}
                  autoComplete="name"
                  maxLength={80}
                  {...form.register("fullName")}
                />
              )}
            </Field>
          </div>
          <FormOutcome failure={failure} />
          <div className="flex flex-wrap gap-3">
            <Button type="submit" disabled={isSubmitting}>
              <PenLine aria-hidden />
              {isSubmitting ? text.signing : text.agree}
            </Button>
            <Button type="button" variant="outline" disabled={asking} onClick={() => void ask()}>
              {asking ? text.sending : text.resend}
            </Button>
          </div>
        </form>
      )}
      {sent === null ? <FormOutcome failure={failure} /> : null}
    </div>
  );
}
