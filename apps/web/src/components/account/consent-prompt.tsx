"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { agreeToNotice } from "@/lib/auth/client";

/** Shown when the privacy notice changed since the person agreed: read it, then agree again. */
export function ConsentPrompt({
  noticeVersion,
  text,
}: {
  noticeVersion: string;
  text: { body: string; read: string; agree: string; failed: string };
}) {
  const [state, setState] = useState<"idle" | "busy" | "failed">("idle");

  return (
    <div
      role="region"
      aria-label={text.read}
      className="space-y-3 rounded-lg border bg-accent/40 p-4"
    >
      <p className="text-sm">{text.body}</p>
      <div className="flex flex-wrap items-center gap-3">
        <a
          href="/privacy"
          target="_blank"
          rel="noopener"
          className="text-sm font-medium text-primary underline underline-offset-4"
        >
          {text.read}
        </a>
        <Button
          type="button"
          size="sm"
          disabled={state === "busy"}
          onClick={() => {
            setState("busy");
            agreeToNotice(noticeVersion).then(
              () => {
                window.location.reload();
              },
              () => {
                setState("failed");
              },
            );
          }}
        >
          {text.agree}
        </Button>
        {state === "failed" ? (
          <p role="alert" className="text-sm text-destructive">
            {text.failed}
          </p>
        ) : null}
      </div>
    </div>
  );
}
