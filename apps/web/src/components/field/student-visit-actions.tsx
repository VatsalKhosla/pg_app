"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/fields";
import { ApiError } from "@/lib/api/errors";
import { checkIn, type Outcome, recordOutcome } from "@/lib/visits/client";

const OUTCOMES: readonly Outcome[] = ["interested", "not_interested", "student_no_show"];

/**
 * An agent at a student's visit (step 3.7): check in from the building, the phone saying where
 * they are (the visit log), then say how it went. Nothing is chosen for them.
 */
export function StudentVisitActions({ id, checkedIn }: { id: string; checkedIn: boolean }) {
  const t = useTranslations("Field.studentVisits.detail");
  const router = useRouter();
  const name = useId();
  const [state, setState] = useState<"idle" | "locating" | "saving">("idle");
  const [failure, setFailure] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [note, setNote] = useState("");

  function refused(error: unknown) {
    if (error instanceof ApiError && error.code === "CHECK_IN_TOO_EARLY") {
      setFailure(t("tooEarly"));
    } else {
      const detail =
        error instanceof ApiError ? (error.problem?.detail ?? error.message) : String(error);
      setFailure(t("failed", { detail }));
    }
  }

  function locate() {
    setFailure(null);
    if (!("geolocation" in navigator)) {
      setFailure(t("noLocation"));
      return;
    }
    setState("locating");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        void (async () => {
          try {
            await checkIn(
              id,
              { lat: position.coords.latitude, lng: position.coords.longitude },
              position.coords.accuracy,
            );
            router.refresh();
          } catch (error) {
            refused(error);
          } finally {
            setState("idle");
          }
        })();
      },
      () => {
        setState("idle");
        setFailure(t("noLocation"));
      },
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 },
    );
  }

  return (
    <div className="space-y-4">
      {checkedIn ? (
        <form
          method="post"
          className="space-y-4 rounded-2xl border border-border/80 bg-card p-6 shadow-xs"
          onSubmit={(event) => {
            event.preventDefault();
            if (outcome === null) return;
            setState("saving");
            setFailure(null);
            void recordOutcome(id, outcome, note.trim())
              .then(() => {
                router.refresh();
              })
              .catch(refused)
              .finally(() => {
                setState("idle");
              });
          }}
        >
          <fieldset className="space-y-2">
            <legend className="font-medium text-foreground">{t("outcome")}</legend>
            {OUTCOMES.map((value) => (
              <label
                key={value}
                className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-border/80 bg-background px-3.5 py-2.5 text-sm transition-colors has-[:checked]:border-primary has-[:checked]:bg-primary-soft/50"
              >
                <input
                  type="radio"
                  name={name}
                  value={value}
                  checked={outcome === value}
                  onChange={() => {
                    setOutcome(value);
                  }}
                  className="size-4 accent-primary"
                />
                {t(value)}
              </label>
            ))}
          </fieldset>
          <label className="block space-y-1.5 text-sm">
            <span className="font-medium text-foreground">{t("note")}</span>
            <Textarea
              value={note}
              maxLength={500}
              rows={3}
              onChange={(event) => {
                setNote(event.target.value);
              }}
            />
          </label>
          <Button type="submit" shape="pill" disabled={outcome === null || state !== "idle"}>
            {state === "saving" ? t("saving") : t("save")}
          </Button>
        </form>
      ) : (
        <Button size="lg" shape="pill" onClick={locate} disabled={state !== "idle"}>
          {state === "locating" ? t("locating") : t("checkIn")}
        </Button>
      )}
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
    </div>
  );
}
