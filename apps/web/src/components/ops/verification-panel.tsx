"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { z } from "@/lib/forms/zod";
import { bookVisit, type Listing, suspendVerification } from "@/lib/ops/client";

import { Field, FormOutcome, Select, Textarea } from "@/components/ui/fields";
import { useOpsProblem } from "./problems";
import { useRefresh } from "./use-refresh";

/** The API's limit for a reason (apps/api/src/app/modules/catalog/domain/verification.py). */
const REASON_MAX = 500;

export interface AgentChoice {
  id: string;
  name: string | null;
}

/**
 * What ops can do about a listing's verification now, as the API says (`canBookVisit`,
 * `canSuspend`): book a field agent's visit, or suspend a verification.
 */
export function VerificationPanel({
  listing,
  agents,
}: {
  listing: Listing;
  agents: AgentChoice[];
}) {
  return (
    <div className="space-y-6">
      {listing.canBookVisit ? <BookVisit listingId={listing.id} agents={agents} /> : null}
      {listing.canSuspend ? <Suspend listingId={listing.id} /> : null}
    </div>
  );
}

function BookVisit({ listingId, agents }: { listingId: string; agents: AgentChoice[] }) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    agent: z.string().min(1, t("validation.choose")),
    // The browser's own time, as the person sees it; sent with its offset.
    when: z
      .string()
      .refine((text) => !Number.isNaN(new Date(text).getTime()), t("validation.required")),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { agent: "", when: "" },
  });
  const { errors, isSubmitting } = form.formState;

  if (agents.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("visits.noAgents")}</p>;
  }

  async function book(values: Values) {
    setFailure(null);
    try {
      await bookVisit(listingId, values.agent, new Date(values.when).toISOString());
      form.reset();
      refresh();
    } catch (error) {
      setFailure(problem(error));
    }
  }

  return (
    <form
      noValidate
      aria-labelledby={`${id}-title`}
      className="space-y-4 rounded-md border p-4"
      onSubmit={(event) => {
        void form.handleSubmit(book)(event);
      }}
    >
      <h3 id={`${id}-title`} className="font-medium">
        {t("visits.book")}
      </h3>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id={`${id}-agent`} label={t("visits.agent")} error={errors.agent?.message}>
          {(control) => (
            <Select {...control} {...form.register("agent")}>
              <option value="">{t("visits.agentChoose")}</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name ?? t("visits.unnamed")}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field id={`${id}-when`} label={t("visits.when")} error={errors.when?.message}>
          {(control) => <Input {...control} type="datetime-local" {...form.register("when")} />}
        </Field>
      </div>
      <FormOutcome failure={failure} />
      <Button type="submit" size="lg" disabled={isSubmitting}>
        {isSubmitting ? t("visits.booking") : t("visits.bookButton")}
      </Button>
    </form>
  );
}

function Suspend({ listingId }: { listingId: string }) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    reason: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .max(REASON_MAX, t("validation.tooLong")),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { reason: "" },
  });

  async function suspend({ reason }: { reason: string }) {
    setFailure(null);
    try {
      await suspendVerification(listingId, reason);
      refresh();
    } catch (error) {
      setFailure(problem(error));
    }
  }

  if (!open) {
    return (
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          setOpen(true);
        }}
      >
        {t("visits.suspend")}
      </Button>
    );
  }
  return (
    <form
      noValidate
      className="space-y-4 rounded-md border border-destructive/40 p-4"
      onSubmit={(event) => {
        void form.handleSubmit(suspend)(event);
      }}
    >
      <p className="text-sm">{t("visits.suspendHint")}</p>
      <Field
        id={`${id}-reason`}
        label={t("visits.reason")}
        error={form.formState.errors.reason?.message}
      >
        {(control) => <Textarea {...control} rows={2} {...form.register("reason")} />}
      </Field>
      <FormOutcome failure={failure} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="destructive" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? t("visits.suspending") : t("visits.suspendConfirm")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setOpen(false);
          }}
        >
          {t("rooms.cancel")}
        </Button>
      </div>
    </form>
  );
}
