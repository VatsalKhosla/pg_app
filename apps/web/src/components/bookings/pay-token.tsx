"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import {
  type CheckoutCallback,
  finishCheckout,
  payAtTestBank,
  type PaymentStart,
  startTokenPayment,
} from "@/lib/payments/client";
import { openRazorpayCheckout } from "@/lib/payments/razorpay";

export interface PayTokenText {
  /** With the booking's token already in words. */
  pay: string;
  /** What Razorpay's checkout says this is for. */
  description: string;
  opening: string;
  checking: string;
  /** The bank hasn't finished, or the gateway can't say yet. */
  waiting: string;
  checkAgain: string;
  notPaid: string;
  /** The money came in, but the booking had moved on. */
  late: string;
  /** The API wouldn't accept what came back: nothing moved. */
  unverified: string;
  /** The booking isn't waiting for its token any more. */
  changed: string;
  /** Payments can't be reached right now. */
  failed: string;
  backToBooking: string;
  test: { title: string; body: string; pay: string; cancel: string };
}

type State =
  | { step: "idle"; notice?: "notPaid" | "failed" | "changed" }
  | { step: "opening" }
  | { step: "testBank"; start: PaymentStart }
  | { step: "checking"; start: PaymentStart; callback: CheckoutCallback }
  | { step: "waiting"; start: PaymentStart; callback: CheckoutCallback }
  | { step: "late" }
  | { step: "unverified" };

// How long to wait before asking again while a bank finishes, each longer than the last. After
// these the student can ask again themselves; a webhook moves the booking anyway.
const WAITS_MS = [2_000, 4_000, 8_000, 16_000] as const;

/**
 * Paying a held booking's token (step 6.1, ADR 0056): an order from the API for exactly the token,
 * Razorpay's checkout (or, on a test copy, the fake gateway's test bank), then the API's own check
 * with the gateway, which alone moves the booking. Everything here can be asked again safely.
 */
export function PayToken({
  code,
  bookingPath,
  text,
}: {
  code: string;
  /** Where to go once it's paid: a full page load, leaving this page's wider policy behind. */
  bookingPath: string;
  text: PayTokenText;
}) {
  const [state, setState] = useState<State>({ step: "idle" });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(
    () => () => {
      clearTimeout(timer.current);
    },
    [],
  );

  function check(start: PaymentStart, callback: CheckoutCallback, tries = 0) {
    setState({ step: "checking", start, callback });
    const again = () => {
      setState({ step: "waiting", start, callback });
      const wait = WAITS_MS[tries];
      if (wait !== undefined) {
        timer.current = setTimeout(() => {
          check(start, callback, tries + 1);
        }, wait);
      }
    };
    finishCheckout(start.id, callback)
      .then((result) => {
        switch (result.outcome) {
          case "paid":
            window.location.assign(bookingPath);
            return;
          case "late":
            setState({ step: "late" });
            return;
          case "not_paid":
            setState({ step: "idle", notice: "notPaid" });
            return;
          case "waiting":
            again();
        }
      })
      .catch((error: unknown) => {
        // Refused: this answer will never be accepted. Anything else may pass, and the student
        // has paid, so it's kept to ask about again.
        if (error instanceof ApiError && error.status < 500) {
          setState({ step: "unverified" });
          return;
        }
        again();
      });
  }

  function pay() {
    setState({ step: "opening" });
    startTokenPayment(code)
      .then(async (start) => {
        if (start.provider === "fake") {
          setState({ step: "testBank", start });
          return;
        }
        const end = await openRazorpayCheckout(start, text.description);
        if (end.kind === "paid") check(start, end.callback);
        else setState({ step: "idle" });
      })
      .catch((error: unknown) => {
        const changed = error instanceof ApiError && error.code === "INVALID_TRANSITION";
        setState({ step: "idle", notice: changed ? "changed" : "failed" });
      });
  }

  function payAtBank(start: PaymentStart) {
    setState({ step: "opening" });
    payAtTestBank(start.id)
      .then((callback) => {
        check(start, callback);
      })
      .catch(() => {
        setState({ step: "idle", notice: "failed" });
      });
  }

  switch (state.step) {
    case "idle":
      return (
        <div className="space-y-3">
          <Button onClick={pay}>{text.pay}</Button>
          {state.notice === undefined ? null : (
            <div role="alert" className="space-y-2 text-sm text-destructive">
              <p>{text[state.notice]}</p>
              {state.notice === "changed" ? (
                <a href={bookingPath} className="font-medium underline underline-offset-4">
                  {text.backToBooking}
                </a>
              ) : null}
            </div>
          )}
        </div>
      );
    case "opening":
      return <p role="status">{text.opening}</p>;
    case "testBank":
      return (
        <section aria-labelledby="test-bank-title" className="space-y-3 rounded-lg border p-4">
          <h2 id="test-bank-title" className="font-semibold">
            {text.test.title}
          </h2>
          <p>{text.test.body}</p>
          <div className="flex flex-wrap gap-3">
            <Button
              onClick={() => {
                payAtBank(state.start);
              }}
            >
              {text.test.pay}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setState({ step: "idle" });
              }}
            >
              {text.test.cancel}
            </Button>
          </div>
        </section>
      );
    case "checking":
      return <p role="status">{text.checking}</p>;
    case "waiting":
      return (
        <div className="space-y-3">
          <p role="status">{text.waiting}</p>
          <Button
            variant="outline"
            onClick={() => {
              clearTimeout(timer.current);
              check(state.start, state.callback);
            }}
          >
            {text.checkAgain}
          </Button>
        </div>
      );
    case "late":
    case "unverified":
      return (
        <div role="alert" className="space-y-2">
          <p>{state.step === "late" ? text.late : text.unverified}</p>
          <a href={bookingPath} className="font-medium underline underline-offset-4">
            {text.backToBooking}
          </a>
        </div>
      );
  }
}
