"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { BOOKINGS_PATH, SIGN_IN_PATH, signInUrl } from "@/lib/auth/routes";
import { holdBed } from "@/lib/bookings/client";
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
  /** At the student's visit (step 5.9), or wherever the API says no visit is needed. */
  reserve: {
    note: string;
    submit: string;
    reserving: string;
    errors: Record<string, string>;
  };
}

// The codes whose message the API completes with what it found.
const WITH_DETAIL: readonly string[] = ["QUOTE_INVALID"];
const RESERVE_WITH_DETAIL: readonly string[] = ["VISIT_NOT_ON_SITE", "HOLD_LIMIT_REACHED"];
const TIME = new Intl.DateTimeFormat("en-IN", { timeStyle: "short", timeZone: "Asia/Kolkata" });

/**
 * A student's own price for a room, move-in and stay (step 4.5, ADR 0040): a quote from the API,
 * shown with how it was worked out, the token, what's due at move-in, the deposit and the other
 * charges (CLAUDE.md rule 7). The browser formats amounts; it never works one out.
 *
 * At their visit (``visit``, step 5.9), the student can reserve the bed at that price on the
 * spot, once the agent has checked in; the booking's page then takes them on. Where the API says
 * no visit is needed (ADR 0058), they can from here, signing in first if they haven't.
 */
export function QuoteChecker({
  rooms,
  stays,
  defaultStay,
  today,
  visit = null,
  text,
}: {
  rooms: readonly { id: string; label: string }[];
  stays: readonly { value: number; label: string }[];
  defaultStay: number;
  /** Today in India, YYYY-MM-DD: the earliest move-in. */
  today: string;
  /** The student's visit to this PG, when they came from it to reserve on the spot. */
  visit?: string | null;
  text: QuoteCheckerText;
}) {
  const id = useId();
  const router = useRouter();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  // One key per quote: a retry of the same reservation replays its first answer.
  const [reservation, setReservation] = useState<string | null>(null);
  const [reserving, setReserving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
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
    setRefused(null);
    try {
      setQuote(await createQuote(values.room, values.moveIn, Number(values.stay)));
      setReservation(crypto.randomUUID());
    } catch (error) {
      setQuote(null);
      setFailure(problemMessage(error, text.errors, WITH_DETAIL));
    }
  }

  async function reserve(quoteId: string, key: string) {
    setReserving(true);
    setRefused(null);
    try {
      const booking = await holdBed(quoteId, visit, key);
      router.push(`${BOOKINGS_PATH}/${booking.code}` as Route);
    } catch (error) {
      if (visit === null && error instanceof ApiError && error.status === 401) {
        router.push(signInUrl(SIGN_IN_PATH, window.location.pathname));
        return;
      }
      setRefused(problemMessage(error, text.reserve.errors, RESERVE_WITH_DETAIL));
      setReserving(false);
    }
  }

  const canReserve = visit !== null || quote?.reserveWithoutVisit === true;

  return (
    <div className="relative space-y-5">
      <form
        method="get"
        noValidate
        className="grid gap-4"
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
        <Button type="submit" size="lg" shape="pill" disabled={isSubmitting} className="w-full">
          {isSubmitting ? text.checking : text.submit}
        </Button>
      </form>
      {failure === null ? null : (
        <p role="alert" className="text-sm font-medium text-destructive">
          {failure}
        </p>
      )}
      <div aria-live="polite">
        {quote === null ? null : (
          <div className="space-y-4 rounded-2xl bg-surface-warm p-4 text-foreground">
            <div className="space-y-1">
              <p className="text-title-3 font-semibold tabular-nums">
                {fillBlanks(text.monthly, { amount: formatINR(quote.monthlyRentPaise) })}
              </p>
              <p className="text-sm text-muted-foreground tabular-nums">{quote.explanation}</p>
            </div>
            <ul className="grid gap-1.5 border-y py-3 text-sm tabular-nums">
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
            <p className="text-sm font-medium text-muted-foreground">
              {fillBlanks(text.validUntil, { time: TIME.format(new Date(quote.expiresAt)) })}{" "}
              {canReserve ? null : text.bookingSoon}
            </p>
            {!canReserve || reservation === null ? null : (
              <div className="space-y-3">
                <p className="text-sm text-foreground">{text.reserve.note}</p>
                <Button
                  size="lg"
                  shape="pill"
                  disabled={reserving}
                  onClick={() => {
                    void reserve(quote.id, reservation);
                  }}
                >
                  {reserving ? text.reserve.reserving : text.reserve.submit}
                </Button>
                {refused === null ? null : (
                  <p role="alert" className="text-sm font-medium text-destructive">
                    {refused}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
