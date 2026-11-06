"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { cancelVisit, scheduleVisit } from "@/lib/visits/client";

const CUSTOM = "custom";

/** The API's detail for a refusal, which the console shows as is: it's for staff. */
function detail(error: unknown): string {
  return error instanceof ApiError ? (error.problem?.detail ?? error.message) : String(error);
}

/**
 * Booking a student's visit (step 3.7): one of the times they offered or another, and the agent
 * who meets them. Booking again changes the time or the agent. Then, while it's open, cancelling.
 */
export function StudentVisitForms({
  id,
  offered,
  agents,
  booked,
  open,
}: {
  id: string;
  /** The times the student offered: value (ISO) and label. */
  offered: readonly { value: string; label: string }[];
  agents: readonly { id: string; name: string }[];
  booked: boolean;
  open: boolean;
}) {
  const t = useTranslations("Ops.studentVisits.detail");
  const router = useRouter();
  const formId = useId();
  const [choice, setChoice] = useState(offered[0]?.value ?? CUSTOM);
  const [custom, setCustom] = useState("");
  const [agent, setAgent] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<"schedule" | "cancel" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function act(kind: "schedule" | "cancel", call: () => Promise<unknown>) {
    setBusy(kind);
    setFailure(null);
    try {
      await call();
      router.refresh();
    } catch (error) {
      setFailure(t("failed", { detail: detail(error) }));
    } finally {
      setBusy(null);
    }
  }

  if (!open) return null;
  const at =
    choice === CUSTOM
      ? custom === ""
        ? ""
        : new Date(`${custom}:00+05:30`).toISOString()
      : choice;
  return (
    <div className="space-y-6">
      <form
        className="space-y-4 rounded-xl border border-border/80 bg-surface/40 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (at === "" || agent === "") return;
          void act("schedule", () => scheduleVisit(id, at, agent));
        }}
      >
        <h2 className="text-lg font-semibold">{booked ? t("reschedule") : t("schedule")}</h2>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">{t("time")}</legend>
          {offered.map((option) => (
            <label
              key={option.value}
              className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-border/80 bg-background px-3.5 py-2 text-sm transition-colors hover:bg-surface/60 has-[:checked]:border-primary has-[:checked]:bg-primary-soft/50"
            >
              <input
                type="radio"
                name={`${formId}-time`}
                value={option.value}
                checked={choice === option.value}
                onChange={() => {
                  setChoice(option.value);
                }}
                className="size-4 accent-primary"
              />
              {option.label}
            </label>
          ))}
          <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-border/80 bg-background px-3.5 py-2 text-sm transition-colors hover:bg-surface/60 has-[:checked]:border-primary has-[:checked]:bg-primary-soft/50">
            <input
              type="radio"
              name={`${formId}-time`}
              value={CUSTOM}
              checked={choice === CUSTOM}
              onChange={() => {
                setChoice(CUSTOM);
              }}
              className="size-4 accent-primary"
            />
            {t("customTime")}
          </label>
          {choice === CUSTOM ? (
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">{t("customTimeField")}</span>
              <Input
                type="datetime-local"
                value={custom}
                onChange={(event) => {
                  setCustom(event.target.value);
                }}
              />
            </label>
          ) : null}
        </fieldset>
        <label className="block space-y-1.5 text-sm">
          <span className="font-medium">{t("agent")}</span>
          <Select
            value={agent}
            onChange={(event) => {
              setAgent(event.target.value);
            }}
          >
            <option value="">{agents.length === 0 ? t("noAgents") : t("chooseAgent")}</option>
            {agents.map((each) => (
              <option key={each.id} value={each.id}>
                {each.name}
              </option>
            ))}
          </Select>
        </label>
        <p className="text-sm text-muted-foreground">{t("texted")}</p>
        <Button type="submit" disabled={busy !== null || at === "" || agent === ""}>
          {busy === "schedule" ? t("saving") : t("save")}
        </Button>
      </form>
      <form
        className="space-y-3 rounded-xl border border-border/80 bg-surface/40 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (reason.trim() === "") return;
          void act("cancel", () => cancelVisit(id, reason.trim()));
        }}
      >
        <h2 className="text-lg font-semibold">{t("cancel")}</h2>
        <label className="block space-y-1.5 text-sm">
          <span className="font-medium">{t("reason")}</span>
          <Input
            value={reason}
            maxLength={500}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
        </label>
        <Button type="submit" variant="outline" disabled={busy !== null || reason.trim() === ""}>
          {busy === "cancel" ? t("cancelling") : t("cancel")}
        </Button>
      </form>
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
    </div>
  );
}
