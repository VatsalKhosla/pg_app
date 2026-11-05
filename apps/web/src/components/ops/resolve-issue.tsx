"use client";

import { useId, useState } from "react";

import { problemMessage } from "@/components/auth/problem-message";
import { useRefresh } from "@/components/ops/use-refresh";
import { Button } from "@/components/ui/button";
import { Field, Textarea } from "@/components/ui/fields";
import { resolveIssue } from "@/lib/invoices/client";

export interface ResolveIssueText {
  open: string;
  label: string;
  confirm: string;
  back: string;
  need: string;
  /** Someone else closed it first. */
  closed: string;
  failed: string;
}

/** Ops close what reconciliation found, saying what they did (step 6.6, ADR 0062). */
export function ResolveIssue({ id, text }: { id: string; text: ResolveIssueText }) {
  const refresh = useRefresh();
  const formId = useId();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [resolution, setResolution] = useState("");
  const [need, setNeed] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  function close() {
    if (resolution.trim() === "") {
      setNeed(true);
      return;
    }
    setNeed(false);
    setBusy(true);
    setFailure(null);
    resolveIssue(id, resolution.trim())
      .then(() => {
        refresh();
      })
      .catch((error: unknown) => {
        setFailure(
          problemMessage(error, { generic: text.failed, INVALID_TRANSITION: text.closed }),
        );
        setBusy(false);
        refresh();
      });
  }

  if (!open) {
    return (
      <Button
        variant="outline"
        onClick={() => {
          setOpen(true);
        }}
      >
        {text.open}
      </Button>
    );
  }
  return (
    <div className="space-y-3">
      <Field id={`${formId}-resolution`} label={text.label} error={need ? text.need : undefined}>
        {(control) => (
          <Textarea
            {...control}
            rows={2}
            maxLength={500}
            value={resolution}
            onChange={(event) => {
              setResolution(event.target.value);
            }}
          />
        )}
      </Field>
      <div className="flex flex-wrap gap-3">
        <Button disabled={busy} onClick={close}>
          {text.confirm}
        </Button>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => {
            setNeed(false);
            setOpen(false);
          }}
        >
          {text.back}
        </Button>
      </div>
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
    </div>
  );
}
