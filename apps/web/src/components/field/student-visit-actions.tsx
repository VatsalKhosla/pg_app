"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
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
          className="space-y-4"
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
          <fieldset className="space-y-1">
            <legend className="font-medium">{t("outcome")}</legend>
            {OUTCOMES.map((value) => (
              <label key={value} className="flex min-h-11 items-center gap-3">
                <input
                  type="radio"
                  name={name}
                  value={value}
                  checked={outcome === value}
                  onChange={() => {
                    setOutcome(value);
                  }}
                  className="size-5 accent-primary"
                />
                {t(value)}
              </label>
            ))}
          </fieldset>
          <label className="block space-y-1.5 text-sm">
            <span className="font-medium">{t("note")}</span>
            <textarea
              value={note}
              maxLength={500}
              rows={3}
              onChange={(event) => {
                setNote(event.target.value);
              }}
              className="w-full rounded-md border bg-background px-3 py-2 text-base shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 md:text-sm dark:bg-input/30"
            />
          </label>
          <Button type="submit" disabled={outcome === null || state !== "idle"}>
            {state === "saving" ? t("saving") : t("save")}
          </Button>
        </form>
      ) : (
        <Button size="lg" onClick={locate} disabled={state !== "idle"}>
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
