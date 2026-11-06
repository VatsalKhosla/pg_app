"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cancelMyVisit } from "@/lib/visits/client";

/** A student's own visit, cancelled: nothing to confirm, as nothing is lost by it. */
export function CancelMyVisit({
  id,
  text,
}: {
  id: string;
  text: { cancel: string; cancelling: string; failed: string };
}) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "busy" | "failed">("idle");
  return (
    <div className="space-y-1.5">
      <Button
        variant="outline"
        size="sm"
        shape="pill"
        disabled={state === "busy"}
        onClick={() => {
          setState("busy");
          cancelMyVisit(id)
            .then(() => {
              router.refresh();
            })
            .catch(() => {
              setState("failed");
            });
        }}
      >
        {state === "busy" ? text.cancelling : text.cancel}
      </Button>
      {state === "failed" ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {text.failed}
        </p>
      ) : null}
    </div>
  );
}
