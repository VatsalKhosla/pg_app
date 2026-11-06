"use client";

import { useEffect, useId, useRef, useState } from "react";

import { useRefresh } from "@/components/ops/use-refresh";
import { Button, buttonVariants } from "@/components/ui/button";
import { type PayLink, payInvoiceAtTestBank } from "@/lib/invoices/client";

export interface PayInvoiceText {
  /** With the balance already in words. */
  pay: string;
  payNote: string;
  noLink: string;
  test: { title: string; body: string; pay: string; cancel: string; paid: string; failed: string };
}

type State = "idle" | "testBank" | "busy" | "paid" | "failed";

// After the test bank pays, the worker records it in a moment: look again a few times.
const LOOKS_MS = [1_500, 4_000, 8_000] as const;

/**
 * Paying an invoice's balance (step 6.5, ADR 0061): Razorpay's own page for its payment link, in a
 * new tab, or, on a test copy of the site, the fake gateway's test bank right here. Either way only
 * the gateway's word, by webhook, marks the invoice paid.
 */
export function PayInvoice({
  id,
  pay,
  text,
}: {
  id: string;
  pay: PayLink | null;
  text: PayInvoiceText;
}) {
  const refresh = useRefresh();
  const titleId = useId();
  const [state, setState] = useState<State>("idle");
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(
    () => () => {
      timers.current.forEach(clearTimeout);
    },
    [],
  );

  if (pay === null) {
    return <p className="text-sm text-muted-foreground">{text.noLink}</p>;
  }
  if (pay.provider === "razorpay") {
    return (
      <div className="space-y-1">
        <a
          href={pay.url}
          target="_blank"
          rel="noopener noreferrer"
          className={buttonVariants({ shape: "pill" })}
        >
          {text.pay}
        </a>
        <p className="text-sm text-muted-foreground">{text.payNote}</p>
      </div>
    );
  }

  function payAtTestBank() {
    setState("busy");
    payInvoiceAtTestBank(id)
      .then(() => {
        setState("paid");
        timers.current = LOOKS_MS.map((wait) => setTimeout(refresh, wait));
      })
      .catch(() => {
        setState("failed");
      });
  }

  if (state === "paid") {
    return (
      <p role="status" className="text-sm">
        {text.test.paid}
      </p>
    );
  }
  if (state === "idle") {
    return (
      <Button
        shape="pill"
        onClick={() => {
          setState("testBank");
        }}
      >
        {text.pay}
      </Button>
    );
  }
  return (
    <section
      aria-labelledby={titleId}
      className="w-full space-y-3 rounded-xl border border-dashed border-border bg-surface/60 p-4"
    >
      <h3 id={titleId} className="font-semibold">
        {text.test.title}
      </h3>
      <p className="text-sm">{text.test.body}</p>
      <div className="flex flex-wrap gap-3">
        <Button shape="pill" disabled={state === "busy"} onClick={payAtTestBank}>
          {text.test.pay}
        </Button>
        <Button
          variant="outline"
          shape="pill"
          disabled={state === "busy"}
          onClick={() => {
            setState("idle");
          }}
        >
          {text.test.cancel}
        </Button>
      </div>
      {state === "failed" ? (
        <p role="alert" className="text-sm text-destructive">
          {text.test.failed}
        </p>
      ) : null}
    </section>
  );
}
