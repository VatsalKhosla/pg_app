"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { fillBlanks } from "@/lib/content/markdown";
import { z } from "@/lib/forms/zod";
import { formatINR } from "@/lib/money";
import { createQuote, type Quote } from "@/lib/pricing/client";

export interface QuoteCheckerText {
  room: string;
  chooseRoom: string;
  moveIn: string;
  stay: string;
  submit: string;
  checking: string;
  needRoom: string;
  needDate: string;
  /** With {amount}. */
  monthly: string;
  token: string;
  dueAtMoveIn: string;
  deposit: string;
  /** With {monthly} and {once}. */
  charges: string;
  noCharges: string;
  /** With {time}. */
  validUntil: string;
  bookingSoon: string;
  errors: Record<string, string>;
}

// The codes whose message the API completes with what it found.
const WITH_DETAIL: readonly string[] = ["QUOTE_INVALID"];
const TIME = new Intl.DateTimeFormat("en-IN", { timeStyle: "short", timeZone: "Asia/Kolkata" });

/**
 * A student's own price for a room, move-in and stay (step 4.5, ADR 0040): a quote from the API,
 * shown with how it was worked out, the token, what's due at move-in, the deposit and the other
 * charges (CLAUDE.md rule 7). The browser formats amounts; it never works one out.
 */
export function QuoteChecker({
  rooms,
  stays,
  defaultStay,
  today,
  text,
}: {
  rooms: readonly { id: string; label: string }[];
  stays: readonly { value: number; label: string }[];
  defaultStay: number;
  /** Today in India, YYYY-MM-DD: the earliest move-in. */
  today: string;
  text: QuoteCheckerText;
}) {
  const id = useId();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    room: z.string().min(1, text.needRoom),
    moveIn: z.string().regex(/^\d{4}-\d{2}-\d{2}$/u, text.needDate),
    stay: z.string(),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      room: rooms.length === 1 ? (rooms[0]?.id ?? "") : "",
      moveIn: today,
      stay: String(defaultStay),
    },
  });
  const { errors, isSubmitting } = form.formState;

  async function check(values: Values) {
    setFailure(null);
    try {
      setQuote(await createQuote(values.room, values.moveIn, Number(values.stay)));
    } catch (error) {
      setQuote(null);
      setFailure(problemMessage(error, text.errors, WITH_DETAIL));
    }
  }

  return (
    <div className="space-y-5">
      <form
        noValidate
        className="grid gap-4 sm:grid-cols-3 sm:items-end"
        onSubmit={(event) => {
          void form.handleSubmit(check)(event);
        }}
      >
        <Field id={`${id}-room`} label={text.room} error={errors.room?.message}>
          {(control) => (
            <Select {...control} {...form.register("room")}>
              <option value="">{text.chooseRoom}</option>
              {rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field id={`${id}-move-in`} label={text.moveIn} error={errors.moveIn?.message}>
          {(control) => <Input {...control} type="date" min={today} {...form.register("moveIn")} />}
        </Field>
        <Field id={`${id}-stay`} label={text.stay}>
          {(control) => (
            <Select {...control} {...form.register("stay")}>
              {stays.map((stay) => (
                <option key={stay.value} value={stay.value}>
                  {stay.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Button
          type="submit"
          disabled={isSubmitting}
          className="sm:col-span-3 sm:justify-self-start"
        >
          {isSubmitting ? text.checking : text.submit}
        </Button>
      </form>
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
      <div aria-live="polite">
        {quote === null ? null : (
          <div className="space-y-2 rounded-lg border bg-muted/40 p-4">
            <p className="text-xl font-bold">
              {fillBlanks(text.monthly, { amount: formatINR(quote.monthlyRentPaise) })}
            </p>
            <p className="text-sm text-muted-foreground">{quote.explanation}</p>
            <ul className="space-y-1 text-sm">
              <li>{fillBlanks(text.token, { amount: formatINR(quote.tokenPaise) })}</li>
              <li>{fillBlanks(text.dueAtMoveIn, { amount: formatINR(quote.dueAtMoveInPaise) })}</li>
              <li>{fillBlanks(text.deposit, { amount: formatINR(quote.depositPaise) })}</li>
              <li>
                {quote.charges.length === 0
                  ? text.noCharges
                  : fillBlanks(text.charges, {
                      monthly: formatINR(quote.monthlyChargesPaise),
                      once: formatINR(quote.oneTimeChargesPaise),
                    })}
              </li>
            </ul>
            <p className="text-sm text-muted-foreground">
              {fillBlanks(text.validUntil, { time: TIME.format(new Date(quote.expiresAt)) })}{" "}
              {text.bookingSoon}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
