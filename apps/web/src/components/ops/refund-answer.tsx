"use client";

import { useId, useState } from "react";

import { problemMessage } from "@/components/auth/problem-message";
import { useRefresh } from "@/components/ops/use-refresh";
import { Button } from "@/components/ui/button";
import { Field, Textarea } from "@/components/ui/fields";
import { approveRefund, declineRefund } from "@/lib/payments/client";

export interface RefundAnswerText {
  approve: string;
  decline: string;
  declineTitle: string;
  reason: string;
  needReason: string;
  confirmDecline: string;
  back: string;
  /** For the person who asked for the refund. */
  secondPerson: string;
  /** Someone else answered first. */
  answered: string;
  failed: string;
}

type Step = "idle" | "declining" | "busy";

/**
 * A second person's answer to a refund above the threshold (step 6.3, ADR 0059). The API refuses
 * the person who asked, and says so here.
 */
export function RefundAnswer({ id, text }: { id: string; text: RefundAnswerText }) {
  const refresh = useRefresh();
  const formId = useId();
  const [step, setStep] = useState<Step>("idle");
  const [reason, setReason] = useState("");
  const [needReason, setNeedReason] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  function answered(work: Promise<unknown>, from: Step) {
    setStep("busy");
    setFailure(null);
    work
      .then(() => {
        refresh();
      })
      .catch((error: unknown) => {
        setFailure(
          problemMessage(error, {
            generic: text.failed,
            REFUND_NEEDS_SECOND_PERSON: text.secondPerson,
            INVALID_TRANSITION: text.answered,
          }),
        );
        setStep(from);
        refresh();
      });
  }

  function decline() {
    if (reason.trim() === "") {
      setNeedReason(true);
      return;
    }
    setNeedReason(false);
    answered(declineRefund(id, reason.trim()), "declining");
  }

  return (
    <div className="space-y-3">
      {step === "declining" ? (
        <section aria-labelledby={`${formId}-title`} className="space-y-3 rounded-lg border p-4">
          <h3 id={`${formId}-title`} className="font-semibold">
            {text.declineTitle}
          </h3>
          <Field
            id={`${formId}-reason`}
            label={text.reason}
            error={needReason ? text.needReason : undefined}
          >
            {(control) => (
              <Textarea
                {...control}
                rows={2}
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                }}
              />
            )}
          </Field>
          <div className="flex flex-wrap gap-3">
            <Button variant="destructive" onClick={decline}>
              {text.confirmDecline}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setNeedReason(false);
                setStep("idle");
              }}
            >
              {text.back}
            </Button>
          </div>
        </section>
      ) : (
        <div className="flex flex-wrap gap-3">
          <Button
            disabled={step === "busy"}
            onClick={() => {
              answered(approveRefund(id), "idle");
            }}
          >
            {text.approve}
          </Button>
          <Button
            variant="outline"
            disabled={step === "busy"}
            onClick={() => {
              setStep("declining");
            }}
          >
            {text.decline}
          </Button>
        </div>
      )}
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
    </div>
  );
}
