import { ArrowRight, CalendarClock } from "lucide-react";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { NotSetUp } from "@/components/owner/not-set-up";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OWNER_BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";
import { getOwnProfile } from "@/lib/owner/server";
import { cn } from "@/lib/utils";

const FILTERS = ["token_secured", "confirmed", "checked_in", "active"] as const;
// Each status's chip, by what it means for the owner: waiting on them, on its way, living there,
// a problem, or over (grey). The chip's words say it too: colour is never the only sign.
const TONES: Partial<Record<string, string>> = {
  token_secured: "border-marigold-border bg-marigold-soft text-marigold-soft-foreground",
  confirmed: "border-primary/30 bg-primary-soft text-primary-soft-foreground",
  checked_in: "border-dusk-border bg-dusk-soft text-dusk-soft-foreground",
  active: "border-neem-border bg-neem-soft text-neem-soft-foreground",
  disputed: "border-ember-border bg-ember-soft text-ember-soft-foreground",
};
const OVER = "border-border/80 bg-surface text-muted-foreground";
type Filter = (typeof FILTERS)[number];
const PAGE = 50;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner.bookings");
  return { title: t("metaTitle") };
}

/**
 * The owner's bookings inbox (step 7.3): newest first, those waiting for an answer with their
 * deadline, and the visits booked to their PGs in the next two weeks.
 */
export default async function OwnerBookingsPage({ searchParams }: PageProps<"/owner/bookings">) {
  await requireOwner(OWNER_BOOKINGS_PATH);
  const owner = await getOwnProfile();
  if (owner === null) return <NotSetUp />;
  const asked = (await searchParams).status;
  const status: Filter | undefined = FILTERS.find((each) => each === asked);
  const api = await getServerApi();
  const [bookings, visits] = await Promise.all([
    unwrap(api.GET("/v1/owner/bookings", { params: { query: { status, limit: PAGE } } })),
    unwrap(api.GET("/v1/owner/visits", { params: { query: { days: 14 } } })),
  ]);
  const [t, format] = await Promise.all([getTranslations("Owner.bookings"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const day = (date: string) =>
    format.dateTime(new Date(`${date}T00:00:00+05:30`), { dateStyle: "medium" });
  const dayPart = (date: string, part: "month" | "day") =>
    format.dateTime(
      new Date(`${date}T00:00:00+05:30`),
      part === "month"
        ? { month: "short", timeZone: "Asia/Kolkata" }
        : { day: "numeric", timeZone: "Asia/Kolkata" },
    );
  const filters: { href: Route; label: string; current: boolean }[] = [
    { href: OWNER_BOOKINGS_PATH, label: t("all"), current: status === undefined },
    ...FILTERS.map((each) => ({
      href: `${OWNER_BOOKINGS_PATH}?status=${each}` as Route,
      label: t(`status.${each}`),
      current: each === status,
    })),
  ];

  return (
    <>
      <div className="space-y-2">
        <h1 className="text-title-1 font-semibold tracking-tight text-foreground">{t("title")}</h1>
        <p className="text-body text-muted-foreground">{t("intro")}</p>
      </div>
      <nav aria-label={t("filter")} className="flex flex-wrap gap-2">
        {filters.map((filter) => (
          <Link
            key={filter.href}
            href={filter.href}
            aria-current={filter.current ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-full border border-border/80 bg-card px-3.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
              filter.current && "border-primary bg-primary-soft font-semibold text-foreground",
            )}
          >
            {filter.label}
          </Link>
        ))}
      </nav>
      {bookings.items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border bg-surface/60 p-6 text-sm text-muted-foreground">
          {t("none")}
        </p>
      ) : (
        <ul className="space-y-3">
          {bookings.items.map((booking) => {
            const waiting = booking.status === "token_secured";
            const href = `${OWNER_BOOKINGS_PATH}/${booking.code}` as Route;
            return (
              <li
                key={booking.code}
                className={cn(
                  "flex gap-4 rounded-[1.5rem] border bg-card p-4 shadow-sm sm:p-5",
                  waiting ? "border-marigold-border" : "border-border/70",
                )}
              >
                {/* The move-in day at a glance; the line below says it in full. */}
                <div
                  aria-hidden="true"
                  className="flex w-14 shrink-0 flex-col items-center justify-center rounded-xl bg-primary-soft py-2 text-primary-soft-foreground"
                >
                  <span className="text-xs font-semibold uppercase">
                    {dayPart(booking.moveIn, "month")}
                  </span>
                  <span className="text-xl leading-tight font-semibold tabular-nums">
                    {dayPart(booking.moveIn, "day")}
                  </span>
                </div>
                <div className="min-w-0 flex-1 space-y-1.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <Link
                      href={href}
                      aria-label={t("open", { code: booking.code })}
                      className="font-semibold text-primary underline underline-offset-4 hover:text-primary-hover"
                    >
                      {t("line", {
                        code: booking.code,
                        place: booking.property.name,
                        roomType: booking.roomType,
                      })}
                    </Link>
                    <span
                      className={cn(
                        "rounded-full border px-2.5 py-0.5 text-xs font-semibold",
                        TONES[booking.status] ?? OVER,
                      )}
                    >
                      {t(`status.${booking.status}`)}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground tabular-nums">
                    {t("moveIn", {
                      date: day(booking.moveIn),
                      months: booking.stayMonths,
                      rent: formatINR(booking.monthlyRentPaise),
                    })}
                  </p>
                  {waiting && booking.confirmBy !== null ? (
                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-marigold-soft px-3 py-2">
                      <p className="text-sm font-semibold text-marigold-soft-foreground">
                        {t("answerBy", { when: when(booking.confirmBy) })}
                      </p>
                      <Link
                        href={href}
                        className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-sun px-3.5 text-sm font-semibold text-sun-foreground shadow-sm hover:bg-sun-hover"
                      >
                        {t("answer")}
                        <ArrowRight aria-hidden="true" className="size-4" />
                      </Link>
                    </div>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <section
        aria-labelledby="visits-title"
        className="space-y-3 rounded-2xl border border-border/80 bg-card p-5 shadow-xs sm:p-6"
      >
        <h2 id="visits-title" className="text-title-3 font-semibold tracking-tight">
          {t("visitsTitle")}
        </h2>
        {visits.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("visitsNone")}</p>
        ) : (
          <ul className="divide-y divide-border/80 rounded-xl border border-border/80 bg-surface/50">
            {visits.items.map((visit) => (
              <li key={visit.id} className="flex items-start gap-3 px-4 py-3 text-sm">
                <CalendarClock aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
                {visit.student === null
                  ? t("visitNoName", { when: when(visit.scheduledAt), place: visit.place })
                  : t("visit", {
                      when: when(visit.scheduledAt),
                      place: visit.place,
                      student: visit.student,
                    })}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
