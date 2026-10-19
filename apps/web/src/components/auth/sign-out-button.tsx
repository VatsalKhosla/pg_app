"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { signOut } from "@/lib/auth/client";

/** Signs out of this browser, then loads the home page afresh (signed out everywhere on it). */
export function SignOutButton({
  label,
  busyLabel,
  failedLabel,
}: {
  label: string;
  busyLabel: string;
  failedLabel: string;
}) {
  const [state, setState] = useState<"idle" | "busy" | "failed">("idle");

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        type="button"
        variant="outline"
        disabled={state === "busy"}
        onClick={() => {
          setState("busy");
          signOut().then(
            () => {
              // A full load, not router navigation: client navigation keeps the root layout (and
              // its header) as rendered, so only a fresh page drops the ended session everywhere.
              // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- see above
              window.location.assign("/");
            },
            () => {
              setState("failed");
            },
          );
        }}
      >
        {state === "busy" ? busyLabel : label}
      </Button>
      {state === "failed" ? (
        <p role="alert" className="text-sm text-destructive">
          {failedLabel}
        </p>
      ) : null}
    </div>
  );
}
