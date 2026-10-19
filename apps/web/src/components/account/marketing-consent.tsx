"use client";

import { useId, useState } from "react";

import { setMarketingConsent } from "@/lib/auth/client";

/** Offers and news: as easy to stop as to start (DPDP), and off unless chosen. */
export function MarketingConsent({
  initial,
  noticeVersion,
  text,
}: {
  initial: boolean;
  noticeVersion: string;
  text: { label: string; saved: string; failed: string };
}) {
  const id = useId();
  const [on, setOn] = useState(initial);
  const [state, setState] = useState<"idle" | "busy" | "saved" | "failed">("idle");

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="flex items-start gap-3 text-sm">
        <input
          id={id}
          type="checkbox"
          className="mt-0.5 size-5 shrink-0 accent-primary"
          checked={on}
          disabled={state === "busy"}
          onChange={(event) => {
            const wanted = event.target.checked;
            setState("busy");
            setMarketingConsent(wanted, noticeVersion).then(
              () => {
                setOn(wanted);
                setState("saved");
              },
              () => {
                setState("failed");
              },
            );
          }}
        />
        <span>{text.label}</span>
      </label>
      <p role="status" className="text-sm text-muted-foreground">
        {state === "saved" ? text.saved : ""}
      </p>
      {state === "failed" ? (
        <p role="alert" className="text-sm text-destructive">
          {text.failed}
        </p>
      ) : null}
    </div>
  );
}
