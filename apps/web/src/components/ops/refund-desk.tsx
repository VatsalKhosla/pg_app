"use client";

import { useId, useRef, useState } from "react";

import { problemMessage } from "@/components/auth/problem-message";
import { useRefresh } from "@/components/ops/use-refresh";
import { Button } from "@/components/ui/button";
import { Field, Textarea } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { formatINR, paiseToRupeesInput, rupeesToPaise } from "@/lib/money";
import { requestRefund } from "@/lib/payments/client";

export interface RefundDeskText {
  open: string;
  title: string;
  amount: string;
  /** What can still go back, in words. */
  left: string;
  reason: string;
  needAmount: string;
  needReason: string;
  next: string;
  /** With the amount filled in by this component, from what ops typed. */
  confirmTitle: string;
  /** What will happen, depending on whether a second person has to agree. */
  confirmBody: string;
  confirmWaits: string;
  yes: string;
  back: string;
  close: string;
  sent: string;
  waits: string;
  /** The API says it's more than is left: its own words follow. */
  tooMuch: string;
  failed: string;
}

type Step = "closed" | "asking" | "confirming" | "busy";

/**
 * Ops give money back (step 6.3, ADR 0059): how much, within what's left of the payment, and why.
 * Then it says what it will do before it's sent, because it can't be undone. Above the threshold it
 * waits for a second person. The API checks all of this again.
 */
export function RefundDesk({
  paymentId,
  refundablePaise,
  secondPersonAbovePaise,
  text,
}: {
  paymentId: string;
  refundablePaise: number;
  secondPersonAbovePaise: number;
  text: RefundDeskText;
}) {
  const refresh = useRefresh();
  const id = useId();
  const [step, setStep] = useState<Step>("closed");
  const [amount, setAmount] = useState(paiseToRupeesInput(refundablePaise));
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<"amount" | "reason" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  // The same key for every try of this one refund, so a retry can't give back twice.
  const key = useRef<string | null>(null);

  const paise = rupeesToPaise(amount);
  const waits = paise !== null && paise > secondPersonAbovePaise;

  function next() {
    setFailure(null);
    if (paise === null || paise <= 0 || paise > refundablePaise) {
      setProblem("amount");
      return;
    }
    if (reason.trim() === "") {
      setProblem("reason");
      return;
    }
    setProblem(null);
    key.current ??= crypto.randomUUID();
    setStep("confirming");
  }

  function send() {
    if (paise === null || key.current === null) return;
    setStep("busy");
    setFailure(null);
    requestRefund(paymentId, paise, reason.trim(), key.current)
      .then((refund) => {
        key.current = null;
        setReason("");
        setStep("closed");
        setDone(refund.status === "awaiting_approval" ? text.waits : text.sent);
        refresh();
      })
      .catch((error: unknown) => {
        setStep("asking");
        setFailure(
          problemMessage(error, { generic: text.failed, REFUND_TOO_MUCH: text.tooMuch }, [
            "REFUND_TOO_MUCH",
          ]),
        );
        // The API said no for good: a new try is a new refund.
        if (error instanceof ApiError && error.status < 500) key.current = null;
        refresh();
      });
  }

  if (step === "closed") {
    return (
      <div className="space-y-2">
        <Button
          variant="outline"
          onClick={() => {
            setDone(null);
            setStep("asking");
          }}
        >
          {text.open}
        </Button>
        {done === null ? null : (
          <p role="status" className="text-sm">
            {done}
          </p>
        )}
      </div>
    );
  }

  if (step === "confirming" || step === "busy") {
    return (
      <section
        aria-labelledby={`${id}-confirm`}
        className="space-y-3 rounded-xl border border-border/80 bg-surface/50 p-4"
      >
        <h3 id={`${id}-confirm`} className="font-semibold">
          {text.confirmTitle.replace("{amount}", paise === null ? "" : formatINR(paise))}
        </h3>
        <p>{waits ? text.confirmWaits : text.confirmBody}</p>
        <div className="flex flex-wrap gap-3">
          <Button variant="destructive" disabled={step === "busy"} onClick={send}>
            {text.yes}
          </Button>
          <Button
            variant="outline"
            disabled={step === "busy"}
            onClick={() => {
              setStep("asking");
            }}
          >
            {text.back}
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-labelledby={`${id}-title`}
      className="space-y-3 rounded-xl border border-border/80 bg-surface/50 p-4"
    >
      <h3 id={`${id}-title`} className="font-semibold">
        {text.title}
      </h3>
      <Field
        id={`${id}-amount`}
        label={text.amount}
        hint={text.left}
        error={problem === "amount" ? text.needAmount : undefined}
      >
        {(control) => (
          <Input
            {...control}
            inputMode="decimal"
            value={amount}
            onChange={(event) => {
              setAmount(event.target.value);
            }}
          />
        )}
      </Field>
      <Field
        id={`${id}-reason`}
        label={text.reason}
        error={problem === "reason" ? text.needReason : undefined}
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
        <Button onClick={next}>{text.next}</Button>
        <Button
          variant="outline"
          onClick={() => {
            setProblem(null);
            setFailure(null);
            setStep("closed");
          }}
        >
          {text.close}
        </Button>
      </div>
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
    </section>
  );
}
