"use client";

import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, FormOutcome } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { resolveAlert } from "@/lib/pricing/alerts-client";

import { useOpsProblem } from "../problems";
import { useRefresh } from "../use-refresh";

const NOTE_MAX = 500;

/** Resolves an alert ops have looked at, with what they found (step 4.8, ADR 0043). */
export function ResolveAlert({ alertId, label }: { alertId: string; label: string }) {
  const t = useTranslations("Ops.alerts");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function resolve() {
    setBusy(true);
    setFailure(null);
    try {
      await resolveAlert(alertId, note.trim());
      refresh();
    } catch (error) {
      setFailure(problem(error));
      setBusy(false);
    }
  }

  return (
    <form
      noValidate
      aria-label={label}
      className="flex flex-wrap items-end gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        void resolve();
      }}
    >
      <Field id={`${id}-note`} label={t("note")} className="min-w-56 flex-1">
        {(control) => (
          <Input
            {...control}
            maxLength={NOTE_MAX}
            value={note}
            onChange={(event) => {
              setNote(event.currentTarget.value);
            }}
          />
        )}
      </Field>
      <Button type="submit" variant="outline" className="h-11" disabled={busy}>
        {busy ? t("resolving") : t("resolve")}
      </Button>
      <div className="basis-full">
        <FormOutcome failure={failure} />
      </div>
    </form>
  );
}
