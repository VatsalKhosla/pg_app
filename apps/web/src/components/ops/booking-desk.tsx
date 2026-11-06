"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { useRefresh } from "@/components/ops/use-refresh";
import { Button } from "@/components/ui/button";
import { Field, FormOutcome, Textarea } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import {
  cancelForOwner,
  confirmForOwner,
  type OpsAction,
  recordMoveOut,
  rejectForOwner,
  remindMoveIn,
} from "@/lib/bookings/ops";
import { z } from "@/lib/forms/zod";

// The API's limit (ADR 0054).
const REASON_MAX = 500;
// The refusal the API completes with why, such as a move-out day that can't be.
const WITH_DETAIL: readonly string[] = ["INVALID_TRANSITION"];

type ReasonedAction = Exclude<OpsAction, "remind_move_in">;

const NEEDS_REASON: readonly ReasonedAction[] = ["confirm", "reject", "owner_cancel", "move_out"];

/**
 * A change that can't be undone: why, for the booking's history, then what it will do, confirmed
 * once more before it's sent.
 */
function ReasonedChange({
  action,
  code,
  today,
  onClose,
}: {
  action: ReasonedAction;
  code: string;
  today: string;
  onClose: () => void;
}) {
  const t = useTranslations("Ops.bookings.actions");
  const id = useId();
  const refresh = useRefresh();
  const asksDay = action === "move_out";
  const schema = z.object({
    reason: z.string().trim().min(1, t("needReason")).max(REASON_MAX, t("needReason")),
    movedOutOn: asksDay
      ? z.string().regex(/^\d{4}-\d{2}-\d{2}$/u, t("needDay"))
      : z.string().optional(),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { reason: "", movedOutOn: asksDay ? today : undefined },
  });
  const { errors } = form.formState;
  const [chosen, setChosen] = useState<Values | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  function send({ reason, movedOutOn }: Values) {
    switch (action) {
      case "confirm":
        return confirmForOwner(code, reason);
      case "reject":
        return rejectForOwner(code, reason);
      case "owner_cancel":
        return cancelForOwner(code, reason);
      case "move_out":
        return recordMoveOut(code, movedOutOn ?? today, reason);
    }
  }

  async function submit(values: Values) {
    setBusy(true);
    setFailure(null);
    try {
      await send(values);
      onClose();
      refresh();
    } catch (error) {
      setChosen(null);
      setFailure(
        problemMessage(
          error,
          { generic: t("failed"), INVALID_TRANSITION: t("refused") },
          WITH_DETAIL,
        ),
      );
      refresh();
    } finally {
      setBusy(false);
    }
  }

  if (chosen !== null) {
    return (
      <section aria-labelledby={`${id}-confirm`} className="space-y-3 rounded-lg border p-4">
        <h3 id={`${id}-confirm`} className="font-semibold">
          {t(`${action}.title`, { code })}
        </h3>
        <p>{t(`${action}.body`)}</p>
        <div className="flex flex-wrap gap-3">
          <Button
            variant={action === "confirm" ? "default" : "destructive"}
            disabled={busy}
            onClick={() => {
              void submit(chosen);
            }}
          >
            {busy ? t("saving") : t(`${action}.yes`)}
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => {
              setChosen(null);
            }}
          >
            {t("back")}
          </Button>
        </div>
      </section>
    );
  }
  return (
    <form
      method="post"
      noValidate
      aria-labelledby={`${id}-title`}
      className="space-y-3 rounded-lg border p-4"
      onSubmit={(event) => {
        void form.handleSubmit((values) => {
          setFailure(null);
          setChosen(values);
        })(event);
      }}
    >
      <h3 id={`${id}-title`} className="font-semibold">
        {t(`${action}.label`)}
      </h3>
      {asksDay ? (
        <Field id={`${id}-day`} label={t("moveOutDay")} error={errors.movedOutOn?.message}>
          {(control) => (
            <Input {...control} type="date" max={today} {...form.register("movedOutOn")} />
          )}
        </Field>
      ) : null}
      <Field
        id={`${id}-reason`}
        label={t("reason")}
        hint={t("reasonHint")}
        error={errors.reason?.message}
      >
        {(control) => (
          <Textarea {...control} rows={2} maxLength={REASON_MAX} {...form.register("reason")} />
        )}
      </Field>
      <FormOutcome failure={failure} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit">{t("next")}</Button>
        <Button type="button" variant="outline" onClick={onClose}>
          {t("close")}
        </Button>
      </div>
    </form>
  );
}

/** Asks a student who has moved in to say so: a text, one a day at most, and nothing else. */
function MoveInNudge({ code }: { code: string }) {
  const t = useTranslations("Ops.bookings.actions");
  const refresh = useRefresh();
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function nudge() {
    setBusy(true);
    setOutcome(null);
    setFailure(null);
    try {
      const { sent } = await remindMoveIn(code);
      setOutcome(sent ? t("remind_move_in.sent") : t("remind_move_in.already"));
    } catch (error) {
      setFailure(
        problemMessage(
          error,
          { generic: t("failed"), INVALID_TRANSITION: t("refused") },
          WITH_DETAIL,
        ),
      );
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">{t("remind_move_in.body")}</p>
      <Button
        variant="outline"
        disabled={busy}
        onClick={() => {
          void nudge();
        }}
      >
        {busy ? t("saving") : t("remind_move_in.label")}
      </Button>
      <FormOutcome failure={failure} {...(outcome === null ? {} : { saved: outcome })} />
    </div>
  );
}

/**
 * What ops may do with a booking now (step 5.10, ADR 0054): exactly what the API says the state
 * machine would take. Each change that can't be undone asks why and then confirms what it does.
 */
export function BookingDesk({
  code,
  actions,
  today,
}: {
  code: string;
  actions: readonly OpsAction[];
  /** Today in India, YYYY-MM-DD: a move-out can't be later. */
  today: string;
}) {
  const t = useTranslations("Ops.bookings.actions");
  const [open, setOpen] = useState<ReasonedAction | null>(null);
  const reasoned = NEEDS_REASON.filter((action) => actions.includes(action));

  return (
    <div className="space-y-4">
      {actions.includes("remind_move_in") ? <MoveInNudge code={code} /> : null}
      {open === null ? (
        <div className="flex flex-wrap gap-3">
          {reasoned.map((action) => (
            <Button
              key={action}
              variant={action === "confirm" ? "default" : "outline"}
              onClick={() => {
                setOpen(action);
              }}
            >
              {t(`${action}.label`)}
            </Button>
          ))}
        </div>
      ) : (
        <ReasonedChange
          key={open}
          action={open}
          code={code}
          today={today}
          onClose={() => {
            setOpen(null);
          }}
        />
      )}
    </div>
  );
}
