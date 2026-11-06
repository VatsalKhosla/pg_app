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
      <label
        htmlFor={id}
        className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-surface/50 p-3.5 text-sm transition-colors hover:bg-accent/50 has-[:checked]:border-primary has-[:checked]:bg-primary-soft/50"
      >
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
        <span className="leading-snug text-foreground">{text.label}</span>
      </label>
      <p role="status" className="text-sm font-medium text-success">
        {state === "saved" ? text.saved : ""}
      </p>
      {state === "failed" ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {text.failed}
        </p>
      ) : null}
    </div>
  );
}
