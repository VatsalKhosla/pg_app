"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { cancelVisit, scheduleVisit } from "@/lib/visits/client";

const fieldClasses =
  "h-11 w-full rounded-md border bg-background px-3 text-base shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 md:text-sm dark:bg-input/30";

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
        className="space-y-4 rounded-lg border p-4"
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
            <label key={option.value} className="flex min-h-11 items-center gap-3 text-sm">
              <input
                type="radio"
                name={`${formId}-time`}
                value={option.value}
                checked={choice === option.value}
                onChange={() => {
                  setChoice(option.value);
                }}
                className="size-5 accent-primary"
              />
              {option.label}
            </label>
          ))}
          <label className="flex min-h-11 items-center gap-3 text-sm">
            <input
              type="radio"
              name={`${formId}-time`}
              value={CUSTOM}
              checked={choice === CUSTOM}
              onChange={() => {
                setChoice(CUSTOM);
              }}
              className="size-5 accent-primary"
            />
            {t("customTime")}
          </label>
          {choice === CUSTOM ? (
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">{t("customTimeField")}</span>
              <input
                type="datetime-local"
                value={custom}
                onChange={(event) => {
                  setCustom(event.target.value);
                }}
                className={fieldClasses}
              />
            </label>
          ) : null}
        </fieldset>
        <label className="block space-y-1.5 text-sm">
          <span className="font-medium">{t("agent")}</span>
          <select
            value={agent}
            onChange={(event) => {
              setAgent(event.target.value);
            }}
            className={fieldClasses}
          >
            <option value="">{agents.length === 0 ? t("noAgents") : t("chooseAgent")}</option>
            {agents.map((each) => (
              <option key={each.id} value={each.id}>
                {each.name}
              </option>
            ))}
          </select>
        </label>
        <p className="text-sm text-muted-foreground">{t("texted")}</p>
        <Button type="submit" disabled={busy !== null || at === "" || agent === ""}>
          {busy === "schedule" ? t("saving") : t("save")}
        </Button>
      </form>
      <form
        className="space-y-3 rounded-lg border p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (reason.trim() === "") return;
          void act("cancel", () => cancelVisit(id, reason.trim()));
        }}
      >
        <h2 className="text-lg font-semibold">{t("cancel")}</h2>
        <label className="block space-y-1.5 text-sm">
          <span className="font-medium">{t("reason")}</span>
          <input
            value={reason}
            maxLength={500}
            onChange={(event) => {
              setReason(event.target.value);
            }}
            className={fieldClasses}
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
