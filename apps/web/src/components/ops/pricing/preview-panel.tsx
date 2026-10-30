"use client";

import { useTranslations } from "next-intl";
import { useEffect, useId, useState } from "react";

import { Field, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { formatINR } from "@/lib/money";
import { addDays, bpsText, dayText, PREVIEW_DAYS } from "@/lib/pricing/editor";
import { type Preview, previewPrice } from "@/lib/pricing/editor-client";

import { useOpsProblem } from "../problems";

const DATE = /^\d{4}-\d{2}-\d{2}$/u;
// Long enough that typing a date asks once, not for every keystroke.
const WAIT_MS = 250;
const CAPS: readonly string[] = ["premium_cap", "discount_cap"];

type Clamp = Preview["clamps"][number];

function DefinitionRow({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-sm font-medium">{term}</dt>
      <dd className="space-y-1 text-sm">{children}</dd>
    </div>
  );
}

/**
 * What a student asking today would be quoted were this version in force (step 4.6, ADR 0041):
 * the API's preview, asked again whenever the room, move-in, stay or the version's rules change.
 * Nothing is stored, and the browser works out no price: it only formats the API's.
 */
export function PreviewPanel({
  ruleSetId,
  revision,
  rooms,
  stays,
  defaultStay,
  today,
}: {
  ruleSetId: string;
  /** Changes whenever the version's rules do, so the preview is asked for again. */
  revision: string;
  rooms: readonly { id: string; label: string }[];
  stays: readonly { value: number; label: string }[];
  defaultStay: number;
  /** Today in India, YYYY-MM-DD. */
  today: string;
}) {
  const t = useTranslations("Ops.pricing.preview");
  const problem = useOpsProblem();
  const id = useId();
  const [room, setRoom] = useState(rooms[0]?.id ?? "");
  const [moveIn, setMoveIn] = useState(today);
  const [stay, setStay] = useState(defaultStay);
  const [result, setResult] = useState<Preview | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (room === "" || !DATE.test(moveIn)) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setBusy(true);
      previewPrice(ruleSetId, { room, moveIn, stay }, controller.signal)
        .then((preview) => {
          setResult(preview);
          setFailure(null);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setResult(null);
          setFailure(problem(error));
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false);
        });
    }, WAIT_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [ruleSetId, revision, room, moveIn, stay, problem]);

  if (rooms.length === 0) return <p>{t("noRooms")}</p>;

  const clampText = (clamp: Clamp) => {
    const amount = (value: number) =>
      CAPS.includes(clamp.kind) ? bpsText(value) : formatINR(value);
    return t(`clamp.${clamp.kind}`, { asked: amount(clamp.asked), allowed: amount(clamp.allowed) });
  };

  return (
    <div className="space-y-5">
      <form
        noValidate
        className="grid gap-4 sm:grid-cols-3"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <Field id={`${id}-room`} label={t("room")}>
          {(control) => (
            <Select
              {...control}
              value={room}
              onChange={(event) => {
                setRoom(event.currentTarget.value);
              }}
            >
              {rooms.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field id={`${id}-move-in`} label={t("moveIn")}>
          {(control) => (
            <Input
              {...control}
              type="date"
              min={today}
              max={addDays(today, PREVIEW_DAYS)}
              value={moveIn}
              onChange={(event) => {
                setMoveIn(event.currentTarget.value);
              }}
            />
          )}
        </Field>
        <Field id={`${id}-stay`} label={t("stay")}>
          {(control) => (
            <Select
              {...control}
              value={String(stay)}
              onChange={(event) => {
                setStay(Number(event.currentTarget.value));
              }}
            >
              {stays.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </form>

      <div aria-live="polite" className="space-y-1">
        {failure === null ? null : <p className="text-sm text-destructive">{failure}</p>}
        {result === null ? null : (
          <p className="text-xl font-semibold">
            {t("monthly", { amount: formatINR(result.monthlyRentPaise) })}
          </p>
        )}
        {busy ? <p className="text-sm text-muted-foreground">{t("checking")}</p> : null}
      </div>

      {result === null ? null : (
        // While the next answer comes, the last one stays, dimmed: no jump, no flash.
        <div
          className={`space-y-4 transition-opacity motion-reduce:transition-none ${busy ? "opacity-60" : ""}`}
        >
          <p className="text-sm text-muted-foreground">{result.explanation}</p>
          <dl className="grid gap-5 sm:grid-cols-2">
            <DefinitionRow term={t("adjustments")}>
              {result.adjustments.length === 0 ? (
                <p>{t("noAdjustments")}</p>
              ) : (
                <ul className="space-y-1">
                  {result.adjustments.map((adjustment) => (
                    <li key={`${adjustment.kind}-${adjustment.label}`}>
                      {adjustment.label}{" "}
                      {adjustment.bps === null
                        ? formatINR(adjustment.rentPaise ?? 0)
                        : bpsText(adjustment.bps)}
                    </li>
                  ))}
                </ul>
              )}
            </DefinitionRow>
            {result.clamps.length === 0 ? null : (
              <DefinitionRow term={t("clamps")}>
                <ul className="space-y-1">
                  {result.clamps.map((clamp) => (
                    <li key={clamp.kind}>{clampText(clamp)}</li>
                  ))}
                </ul>
              </DefinitionRow>
            )}
            <DefinitionRow term={t("student")}>
              <p>{t("token", { amount: formatINR(result.tokenPaise) })}</p>
              <p>{t("due", { amount: formatINR(result.dueAtMoveInPaise) })}</p>
              <p>{t("deposit", { amount: formatINR(result.depositPaise) })}</p>
              <p>
                {t("charges", {
                  monthly: formatINR(result.monthlyChargesPaise),
                  once: formatINR(result.oneTimeChargesPaise),
                })}
              </p>
            </DefinitionRow>
            <DefinitionRow term={t("owner")}>
              <p>
                {t("fee", {
                  fee: formatINR(result.feePaise),
                  gst: formatINR(result.gstPaise),
                  total: formatINR(result.ownerFeeTotalPaise),
                })}
              </p>
            </DefinitionRow>
          </dl>
          {result.bookableFrom === null ? null : (
            <p className="text-sm">{t("bookableFrom", { date: dayText(result.bookableFrom) })}</p>
          )}
        </div>
      )}
    </div>
  );
}
