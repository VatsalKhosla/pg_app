"use client";

import { useState } from "react";

import { problemMessage } from "@/components/auth/problem-message";
import { useRefresh } from "@/components/ops/use-refresh";
import { Button } from "@/components/ui/button";
import { askForPaymentLink } from "@/lib/invoices/client";

export interface InvoiceLinkText {
  newLink: string;
  asked: string;
  failed: string;
  /** Paid already, or a link is out. */
  exists: string;
}

/**
 * Ops ask for a new payment link for an invoice whose link was cancelled or refused (step 6.5,
 * ADR 0061). A job asks the gateway; the page shows the link once it's made.
 */
export function InvoiceLink({ id, text }: { id: string; text: InvoiceLinkText }) {
  const refresh = useRefresh();
  const [state, setState] = useState<"idle" | "busy" | "asked">("idle");
  const [failure, setFailure] = useState<string | null>(null);

  function ask() {
    setState("busy");
    setFailure(null);
    askForPaymentLink(id)
      .then(() => {
        setState("asked");
        setTimeout(refresh, 3_000);
      })
      .catch((error: unknown) => {
        setFailure(
          problemMessage(error, { generic: text.failed, INVALID_TRANSITION: text.exists }),
        );
        setState("idle");
        refresh();
      });
  }

  return (
    <div className="space-y-2">
      {state === "asked" ? (
        <p role="status" className="text-sm">
          {text.asked}
        </p>
      ) : (
        <Button variant="outline" disabled={state === "busy"} onClick={ask}>
          {text.newLink}
        </Button>
      )}
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
    </div>
  );
}
