import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { LiveRefresh } from "@/components/ops/live-refresh";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { dayText } from "@/lib/format/days";
import { cn } from "@/lib/utils";

const STATUSES = [
  "held",
  "token_secured",
  "confirmed",
  "checked_in",
  "disputed",
  "active",
  "completed",
  "expired",
  "cancelled",
  "rejected",
  "no_show",
  "refunded",
] as const;
type Status = (typeof STATUSES)[number];
const ATTENTION = "attention";
const ALL = "all";
type Show = Status | typeof ATTENTION | typeof ALL;

const CHANNELS = ["on_spot", "remote"] as const;
type Channel = (typeof CHANNELS)[number];

const SEARCH_MAX_LENGTH = 100;
const PAGE_SIZE = 30;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.bookings");
  return { title: t("metaTitle") };
}

/**
 * The bookings board (step 5.10, ADR 0054): where ops start the day. It opens on what needs a
 * person now, oldest first: an owner past their two hours, a dispute to settle that day, a move-in
 * due. Every status is a click away with its count, and a search finds a booking by its code, a
 * student's phone or a PG's name. It keeps itself current while it's open.
 */
export default async function OpsBookingsPage({ searchParams }: PageProps<"/ops/bookings">) {
  await requireOps(OPS_BOOKINGS_PATH);
  const asked = await searchParams;
  const text = typeof asked.q === "string" ? asked.q.trim().slice(0, SEARCH_MAX_LENGTH) : "";
  const q = text === "" ? undefined : text;
  const channel = CHANNELS.find((each) => each === asked.channel);
  const cursor = typeof asked.cursor === "string" && UUID.test(asked.cursor) ? asked.cursor : null;
  // A search looks through everything unless a status is chosen; otherwise the work comes first.
  const show: Show =
    asked.status === ALL || asked.status === ATTENTION
      ? asked.status
      : (STATUSES.find((each) => each === asked.status) ?? (q === undefined ? ATTENTION : ALL));
  const api = await getServerApi();
  const [summary, page] = await Promise.all([
    unwrap(api.GET("/v1/ops/bookings/summary")),
    unwrap(
      api.GET("/v1/ops/bookings", {
        params: {
          query: {
            status: show === ATTENTION || show === ALL ? undefined : show,
            attention: show === ATTENTION,
            channel,
            q,
            cursor: cursor ?? undefined,
            limit: PAGE_SIZE,
          },
        },
      }),
    ),
  ]);
  const [t, format] = await Promise.all([getTranslations("Ops.bookings"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const counts = new Map(summary.statuses.map((each) => [each.status, each.count]));
  const link = (status: Show, options: { cursor?: string } = {}) => {
    const query = new URLSearchParams({ status });
    if (channel !== undefined) query.set("channel", channel);
    if (q !== undefined) query.set("q", q);
    if (options.cursor !== undefined) query.set("cursor", options.cursor);
    return `${OPS_BOOKINGS_PATH}?${query.toString()}` as Route;
  };
  const filters: { label: string; status: Show }[] = [
    { label: t("attention", { count: summary.attention }), status: ATTENTION },
    ...STATUSES.map((status) => ({
      label: t("statusCount", { status: t(`status.${status}`), count: counts.get(status) ?? 0 }),
      status,
    })),
    { label: t("all"), status: ALL },
  ];

  return (
    <div className="space-y-6">
      <LiveRefresh />
      <div className="space-y-2">
        <h1 className="font-display text-title-1 text-foreground">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
        <p className="text-sm font-medium text-foreground">
          {t("waiting", {
            owners: summary.unconfirmedLate,
            disputes: summary.disputesOpen,
            moveIns: summary.moveInsDue,
          })}
        </p>
      </div>
      <form
        method="get"
        action={OPS_BOOKINGS_PATH}
        className="flex flex-wrap items-end gap-3 rounded-2xl border border-border/80 bg-card p-5 shadow-xs"
      >
        <div className="min-w-56 flex-1 space-y-1">
          <label htmlFor="booking-search" className="text-sm font-medium">
            {t("search")}
          </label>
          <Input
            id="booking-search"
            name="q"
            defaultValue={q}
            maxLength={SEARCH_MAX_LENGTH}
            placeholder={t("searchHint")}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="booking-channel" className="text-sm font-medium">
            {t("channel")}
          </label>
          <Select id="booking-channel" name="channel" defaultValue={channel ?? ""}>
            <option value="">{t("anyChannel")}</option>
            {CHANNELS.map((each: Channel) => (
              <option key={each} value={each}>
                {t(`channels.${each}`)}
              </option>
            ))}
          </Select>
        </div>
        <Button type="submit" variant="outline" className="h-11">
          {t("find")}
        </Button>
      </form>
      <nav aria-label={t("statusFilter")} className="flex flex-wrap gap-2">
        {filters.map((filter) => (
          <Link
            key={filter.status}
            href={link(filter.status)}
            aria-current={filter.status === show ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-full border border-border/80 bg-card px-3.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors outline-none hover:bg-surface hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50",
              filter.status === show &&
                "border-primary bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
            )}
          >
            {filter.label}
          </Link>
        ))}
      </nav>
      {page.items.length === 0 ? (
        <p className="text-muted-foreground">{show === ATTENTION ? t("allClear") : t("none")}</p>
      ) : (
        <ul className="divide-y divide-border/60 rounded-2xl border border-border/80 bg-card shadow-xs">
          {page.items.map((booking) => (
            <li key={booking.code} className="space-y-1 p-4">
              <p className="flex flex-wrap items-center gap-2">
                <Link
                  href={`${OPS_BOOKINGS_PATH}/${booking.code}` as Route}
                  className="font-mono font-semibold text-primary underline-offset-4 hover:underline"
                >
                  {booking.code}
                </Link>
                <span className="font-medium text-foreground">{booking.property.name}</span>
                {booking.timer?.late === true ? (
                  <span className="rounded-full bg-destructive-soft px-2.5 py-0.5 text-xs font-semibold text-destructive-soft-foreground">
                    {t("late")}
                  </span>
                ) : null}
              </p>
              <p className="text-sm text-muted-foreground">
                {t(`status.${booking.status}`)} · {booking.roomType} · {booking.property.locality} ·{" "}
                {booking.student.name ?? t("noName")} · {t(`channels.${booking.channel}`)}
              </p>
              <p className="text-sm tabular-nums">
                {t("moveIn", { date: dayText(booking.moveIn) })}
                {booking.timer === null
                  ? null
                  : ` · ${t(`timer.${booking.timer.kind}`, {
                      since: when(booking.timer.since),
                      due: when(booking.timer.due),
                    })}`}
              </p>
            </li>
          ))}
        </ul>
      )}
      {page.nextCursor === null ? null : (
        <Link
          href={link(show, { cursor: page.nextCursor })}
          className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
        >
          {t("nextPage")}
        </Link>
      )}
    </div>
  );
}
