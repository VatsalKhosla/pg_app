import { AlertTriangle, CalendarClock, Hourglass, KeyRound, type LucideIcon } from "lucide-react";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { StatusBars } from "@/components/ops/status-bars";
import { WeeklyBars } from "@/components/ops/weekly-bars";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_BOOKINGS_PATH, OPS_DISPUTES_PATH } from "@/lib/auth/routes";
import { formatINR } from "@/lib/money";
import { shortRupees } from "@/lib/search/labels";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("OpsDashboard");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

const WEEKS = 12;
const weekLabel = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const count = new Intl.NumberFormat("en-IN");

/**
 * The console's home: what needs a person now, and the last twelve weeks of visits, tokens and fees,
 * with listings and bookings by status. Every number comes from GET /v1/ops/insights.
 */
export default async function OpsDashboardPage() {
  const api = await getServerApi();
  const [data, t, tListing, tBooking] = await Promise.all([
    unwrap(api.GET("/v1/ops/insights", { params: { query: { weeks: WEEKS } } })),
    getTranslations("OpsDashboard"),
    getTranslations("Ops.status"),
    getTranslations("Ops.bookings.status"),
  ]);
  const weeks = data.weeks.map((week) => weekLabel.format(new Date(`${week}T00:00:00Z`)));
  const sum = (values: readonly number[]) => values.reduce((total, each) => total + each, 0);
  const tiles: {
    key: "attention" | "unconfirmedLate" | "disputesOpen" | "moveInsDue";
    Icon: LucideIcon;
    value: number;
    href: Route;
  }[] = [
    {
      key: "attention",
      Icon: AlertTriangle,
      value: data.board.attention,
      href: `${OPS_BOOKINGS_PATH}?attention=true` as Route,
    },
    {
      key: "unconfirmedLate",
      Icon: Hourglass,
      value: data.board.unconfirmedLate,
      href: `${OPS_BOOKINGS_PATH}?attention=true` as Route,
    },
    {
      key: "disputesOpen",
      Icon: KeyRound,
      value: data.board.disputesOpen,
      href: OPS_DISPUTES_PATH,
    },
    {
      key: "moveInsDue",
      Icon: CalendarClock,
      value: data.board.moveInsDue,
      href: `${OPS_BOOKINGS_PATH}?attention=true` as Route,
    },
  ];
  const chart = { tableLabel: t("table"), weekLabel: t("week"), weeks };

  return (
    <div className="space-y-6">
      <header className="scope-night relative isolate overflow-hidden rounded-[2rem] p-7 sm:p-9">
        <div aria-hidden="true" className="sky-band absolute inset-0 -z-10" />
        <h1 className="text-display font-medium">{t("title")}</h1>
        <p className="mt-2 text-night-foreground">{t("period", { weeks: WEEKS })}</p>
      </header>

      <ul className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {tiles.map(({ key, Icon, value, href }) => (
          <li key={key}>
            <Link
              href={href}
              className="flex h-full flex-col gap-3 rounded-[1.5rem] border border-border/70 bg-card p-5 shadow-md outline-none transition-shadow hover:shadow-lg focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
            >
              <span
                aria-hidden="true"
                className={`grid size-10 place-items-center rounded-xl ${value > 0 ? "bg-warning-soft text-warning-soft-foreground" : "bg-neem-soft text-neem-soft-foreground"}`}
              >
                <Icon className="size-5" />
              </span>
              <span className="text-title-1 font-semibold tabular-nums">{count.format(value)}</span>
              <span className="text-sm text-muted-foreground">{t(`tiles.${key}`)}</span>
            </Link>
          </li>
        ))}
      </ul>

      <div className="grid gap-6 xl:grid-cols-2">
        <WeeklyBars
          id="visits"
          title={t("visits")}
          total={count.format(sum(data.visitsRequested))}
          values={data.visitsRequested}
          axis={(value) => count.format(value)}
          value={(value) => count.format(value)}
          {...chart}
        />
        <WeeklyBars
          id="tokens"
          title={t("tokens")}
          total={count.format(sum(data.tokensSecured))}
          values={data.tokensSecured}
          axis={(value) => count.format(value)}
          value={(value) => count.format(value)}
          {...chart}
        />
        <WeeklyBars
          id="fees"
          title={t("fees")}
          total={formatINR(sum(data.feesInvoicedPaise))}
          values={data.feesInvoicedPaise}
          axis={shortRupees}
          value={formatINR}
          {...chart}
        />
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-1">
          <StatusBars
            id="listings"
            title={t("listings")}
            rows={data.listings.map((item) => ({
              key: item.status,
              label: tListing(item.status),
              count: item.count,
            }))}
          />
          <StatusBars
            id="bookings"
            title={t("bookings")}
            rows={data.board.statuses
              .filter((item) => item.count > 0)
              .map((item) => ({
                key: item.status,
                label: tBooking(item.status),
                count: item.count,
              }))}
          />
        </div>
      </div>
    </div>
  );
}
