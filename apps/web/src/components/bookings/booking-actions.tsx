"use client";

import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { actionsFor } from "@/lib/bookings/actions";
import { cancelMyBooking, type StudentBooking } from "@/lib/bookings/client";

export interface BookingActionsText {
  cancel: string;
  confirmTitle: string;
  /** What cancelling now gives back, the API's amount already in words. */
  refund: string;
  policy: string;
  confirm: string;
  keep: string;
  cancelling: string;
  changed: string;
  failed: string;
  findAnother: string;
}

type Step = "idle" | "asking" | "busy" | "changed" | "failed";

/**
 * What a student can do with their booking now (step 5.5, ADR 0049): cancel it, after seeing what
 * that gives back and confirming; or, once it ended without a stay, look for another PG. Nothing
 * is pre-ticked and nothing counts down here: the refund is the API's, and the API checks it
 * again as the student confirms.
 */
export function BookingActions({
  booking,
  policyPath,
  text,
}: {
  booking: Pick<StudentBooking, "code" | "status" | "cancellation">;
  policyPath: Route;
  text: BookingActionsText;
}) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("idle");
  const actions = actionsFor(booking);
  const { cancellation } = booking;

  function cancel(refundPaise: number) {
    setStep("busy");
    cancelMyBooking(booking.code, refundPaise)
      .then(() => {
        setStep("idle");
        router.refresh();
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.code === "REFUND_CHANGED") {
          setStep("changed");
          router.refresh();
          return;
        }
        setStep("failed");
      });
  }

  return (
    <div className="space-y-4">
      {actions.cancel && cancellation !== null ? (
        step === "idle" || step === "changed" ? (
          <div className="space-y-2">
            <Button
              variant="outline"
              onClick={() => {
                setStep("asking");
              }}
            >
              {text.cancel}
            </Button>
            {step === "changed" ? (
              <p role="alert" className="text-sm text-destructive">
                {text.changed}
              </p>
            ) : null}
          </div>
        ) : (
          <section aria-labelledby="cancel-title" className="space-y-3 rounded-lg border p-4">
            <h3 id="cancel-title" className="font-semibold">
              {text.confirmTitle}
            </h3>
            <p>{text.refund}</p>
            <Link
              href={policyPath}
              className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
            >
              {text.policy}
            </Link>
            <div className="flex flex-wrap gap-3">
              <Button
                variant="destructive"
                disabled={step === "busy"}
                onClick={() => {
                  cancel(cancellation.refundPaise);
                }}
              >
                {step === "busy" ? text.cancelling : text.confirm}
              </Button>
              <Button
                variant="outline"
                disabled={step === "busy"}
                onClick={() => {
                  setStep("idle");
                }}
              >
                {text.keep}
              </Button>
            </div>
            {step === "failed" ? (
              <p role="alert" className="text-sm text-destructive">
                {text.failed}
              </p>
            ) : null}
          </section>
        )
      ) : null}
      {actions.findAnother ? (
        <Link href="/search" className={buttonVariants()}>
          {text.findAnother}
        </Link>
      ) : null}
    </div>
  );
}
