import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { ResolveAlert } from "@/components/ops/pricing/resolve-alert";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_PRICING_ALERTS_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";
import { dayText } from "@/lib/pricing/editor";
import { cn } from "@/lib/utils";

const STATUSES = ["open", "resolved"] as const;
type Status = (typeof STATUSES)[number];
type Alert = Schemas["PricingAlertInfo"];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.alerts");
  return { title: t("metaTitle") };
}

/**
 * Pricing's integrity alerts (ARCHITECTURE §8.7; step 4.8, ADR 0043): the open ones newest
 * first, or the resolved ones, each in a sentence from the numbers that raised it, with the way
 * to its PG's pricing and, while it's open, to resolve it.
 */
export default async function PricingAlertsPage({
  searchParams,
}: PageProps<"/ops/pricing-alerts">) {
  await requireOps(OPS_PRICING_ALERTS_PATH);
  const query = await searchParams;
  const status: Status = query.status === "resolved" ? "resolved" : "open";
  const cursor = typeof query.cursor === "string" && UUID.test(query.cursor) ? query.cursor : null;
  const api = await getServerApi();
  const page = await unwrap(
    api.GET("/v1/ops/pricing-alerts", {
      params: { query: { status, limit: 50, ...(cursor === null ? {} : { cursor }) } },
    }),
  );
  const [t, format] = await Promise.all([getTranslations("Ops.alerts"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });

  const about = (alert: Alert) => {
    const numbers = alert.numbers;
    const week = numbers.week ? dayText(numbers.week, { short: true }) : "";
    switch (alert.kind) {
      case "rent_below_market":
        return t("about.rent_below_market", {
          room: alert.room?.label ?? "",
          listed: formatINR(numbers.listedRentPaise ?? 0),
          median: formatINR(numbers.medianRentPaise ?? 0),
          count: numbers.comparables ?? 0,
          locality: numbers.locality ?? "",
        });
      case "clamps_frequent":
        return t("about.clamps_frequent", {
          clamped: numbers.clamped ?? 0,
          quotes: numbers.quotes ?? 0,
          week,
        });
      case "rule_churn":
        return t("about.rule_churn", { count: numbers.activations ?? 0, week });
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="max-w-prose text-muted-foreground">{t("intro")}</p>
      </div>
      <nav aria-label={t("statusFilter")} className="flex flex-wrap gap-2">
        {STATUSES.map((each) => (
          <Link
            key={each}
            href={`${OPS_PRICING_ALERTS_PATH}?status=${each}` as Route}
            aria-current={each === status ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-full border px-3 text-sm outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50",
              each === status && "border-primary bg-accent font-medium",
            )}
          >
            {t(each)}
          </Link>
        ))}
      </nav>
      {page.items.length === 0 ? (
        <p className="text-muted-foreground">{status === "open" ? t("none") : t("noneResolved")}</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {page.items.map((alert) => (
            <li key={alert.id} className="space-y-3 p-4">
              <div className="space-y-1">
                <h2 className="font-semibold">
                  {`${t(`kinds.${alert.kind}`)}: ${alert.property.name}`}
                </h2>
                <p>{about(alert)}</p>
                <p className="text-sm text-muted-foreground">
                  {t("raised", { when: when(alert.raisedAt) })}
                  {alert.resolvedAt === null
                    ? null
                    : ` · ${t("resolvedOn", { when: when(alert.resolvedAt) })} ${
                        alert.resolvedBy === null
                          ? t("byCheck")
                          : t("resolvedBy", { name: alert.resolvedBy.name ?? t("someone") })
                      }`}
                </p>
                {alert.resolution === "" ? null : <p className="text-sm">{alert.resolution}</p>}
                <Link
                  href={`/ops/listings/${alert.property.id}/pricing` as Route}
                  className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
                >
                  {t("pricing")}
                </Link>
              </div>
              {alert.resolvedAt === null ? (
                <ResolveAlert
                  alertId={alert.id}
                  label={`${t("resolve")}: ${t(`kinds.${alert.kind}`)}, ${alert.property.name}`}
                />
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {page.nextCursor === null ? null : (
        <Link
          href={`${OPS_PRICING_ALERTS_PATH}?status=${status}&cursor=${page.nextCursor}` as Route}
          className="inline-flex min-h-6 items-center font-medium text-primary underline underline-offset-4"
        >
          {t("older")}
        </Link>
      )}
    </div>
  );
}
