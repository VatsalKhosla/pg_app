"use client";

import { useId, useState } from "react";

import { problemMessage } from "@/components/auth/problem-message";
import { useRefresh } from "@/components/ops/use-refresh";
import { Button } from "@/components/ui/button";
import { Field, Textarea } from "@/components/ui/fields";
import { confirmBooking, rejectBooking } from "@/lib/owner/browser";

export interface BookingAnswerText {
  confirm: string;
  reject: string;
  rejectTitle: string;
  reason: string;
  needReason: string;
  confirmReject: string;
  back: string;
  /** The booking moved on, or someone answered first. */
  changed: string;
  failed: string;
}

type Step = "idle" | "rejecting" | "busy";

/** The owner's answer to a booking waiting for it (step 7.3): confirm, or turn it down saying why. */
export function BookingAnswer({ code, text }: { code: string; text: BookingAnswerText }) {
  const refresh = useRefresh();
  const formId = useId();
  const [step, setStep] = useState<Step>("idle");
  const [reason, setReason] = useState("");
  const [needReason, setNeedReason] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  function answer(work: Promise<unknown>, from: Step) {
    setStep("busy");
    setFailure(null);
    work
      .then(() => {
        refresh();
      })
      .catch((error: unknown) => {
        setFailure(
          problemMessage(error, { generic: text.failed, INVALID_TRANSITION: text.changed }),
        );
        setStep(from);
        refresh();
      });
  }

  function reject() {
    if (reason.trim() === "") {
      setNeedReason(true);
      return;
    }
    setNeedReason(false);
    answer(rejectBooking(code, reason.trim()), "rejecting");
  }

  return (
    <div className="space-y-3">
      {step === "rejecting" ? (
        <section aria-labelledby={`${formId}-title`} className="space-y-3 rounded-lg border p-4">
          <h3 id={`${formId}-title`} className="font-semibold">
            {text.rejectTitle}
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
                maxLength={500}
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                }}
              />
            )}
          </Field>
          <div className="flex flex-wrap gap-3">
            <Button variant="destructive" onClick={reject}>
              {text.confirmReject}
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
              answer(confirmBooking(code), "idle");
            }}
          >
            {text.confirm}
          </Button>
          <Button
            variant="outline"
            disabled={step === "busy"}
            onClick={() => {
              setStep("rejecting");
            }}
          >
            {text.reject}
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
