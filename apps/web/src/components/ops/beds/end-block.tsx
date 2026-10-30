"use client";

import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, FormOutcome } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { endBlock } from "@/lib/inventory/client";

import { useOpsProblem } from "../problems";
import { useRefresh } from "../use-refresh";

/** Ends a block: the bed is free from the day chosen; on or before its first day, it's
 * cancelled (step 5.1, ADR 0044). */
export function EndBlock({
  blockId,
  label,
  today,
}: {
  blockId: string;
  label: string;
  today: string;
}) {
  const t = useTranslations("Ops.beds");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [on, setOn] = useState(today);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function end() {
    setBusy(true);
    setFailure(null);
    try {
      await endBlock(blockId, on);
      refresh();
    } catch (error) {
      setFailure(problem(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      noValidate
      aria-label={label}
      className="flex flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        void end();
      }}
    >
      <Field id={`${id}-on`} label={t("freeFrom")} hint={t("endHint")} className="min-w-40">
        {(control) => (
          <Input
            {...control}
            type="date"
            value={on}
            onChange={(event) => {
              setOn(event.currentTarget.value);
            }}
          />
        )}
      </Field>
      <Button type="submit" variant="outline" className="h-11" disabled={busy || on === ""}>
        {busy ? t("ending") : t("end")}
      </Button>
      <div className="basis-full">
        <FormOutcome failure={failure} />
      </div>
    </form>
  );
}
