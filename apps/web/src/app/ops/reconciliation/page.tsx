import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { ResolveIssue } from "@/components/ops/resolve-issue";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_RECONCILIATION_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";
import { cn } from "@/lib/utils";

const PAGE = 50;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.reconciliation");
  return { title: t("metaTitle") };
}

/**
 * Reconciliation (step 6.6, ADR 0062): what's still waiting on the gateway, and what the checks
 * found that a person has to look at, each closed with what was done.
 */
export default async function OpsReconciliationPage({
  searchParams,
}: PageProps<"/ops/reconciliation">) {
  await requireOps(OPS_RECONCILIATION_PATH);
  const everything = (await searchParams).show === "all";
  const api = await getServerApi();
  const [summary, page] = await Promise.all([
    unwrap(api.GET("/v1/ops/reconciliation")),
    unwrap(
      api.GET("/v1/ops/reconciliation/issues", {
        params: { query: { open: !everything, limit: PAGE } },
      }),
    ),
  ]);
  const [t, format] = await Promise.all([getTranslations("Ops.reconciliation"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const counts = [
    { term: t("summary.openIssues"), value: summary.openIssues },
    { term: t("summary.tokensAuthorized"), value: summary.tokensAuthorized },
    { term: t("summary.linksOpen"), value: summary.linksOpen },
    { term: t("summary.refundsWaiting"), value: summary.refundsWaiting },
  ];
  const views: { href: Route; label: string; current: boolean }[] = [
    { href: OPS_RECONCILIATION_PATH, label: t("show.open"), current: !everything },
    {
      href: `${OPS_RECONCILIATION_PATH}?show=all` as Route,
      label: t("show.all"),
      current: everything,
    },
  ];

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="font-display text-title-1 text-foreground">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <section aria-labelledby="waiting-title" className="space-y-3">
        <h2 id="waiting-title" className="font-display text-title-3 text-foreground">
          {t("summary.title")}
        </h2>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {counts.map((count) => (
            <div
              key={count.term}
              className="rounded-2xl border border-border/80 bg-card p-4 shadow-xs"
            >
              <dt className="text-sm text-muted-foreground">{count.term}</dt>
              <dd className="mt-1 font-display text-2xl font-semibold text-foreground tabular-nums">
                {count.value}
              </dd>
            </div>
          ))}
        </dl>
      </section>
      <nav aria-label={t("show.label")} className="flex flex-wrap gap-2">
        {views.map((view) => (
          <Link
            key={view.href}
            href={view.href}
            aria-current={view.current ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-full border border-border/80 bg-card px-3.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-surface hover:text-foreground",
              view.current &&
                "border-primary bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
            )}
          >
            {view.label}
          </Link>
        ))}
      </nav>
      {page.items.length === 0 ? (
        <p className="text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="space-y-4">
          {page.items.map((issue) => (
            <li
              key={issue.id}
              className="space-y-2 rounded-2xl border border-border/80 bg-card p-5 shadow-xs"
            >
              <p className="font-semibold text-foreground">{t(`kind.${issue.kind}`)}</p>
              <p className="text-sm">{issue.detail}</p>
              <p className="text-sm text-muted-foreground tabular-nums">
                {[
                  t("found", { when: when(issue.foundAt) }),
                  issue.booking === null ? null : t("booking", { code: issue.booking }),
                  issue.amountPaise === null
                    ? null
                    : t("amount", { amount: formatINR(issue.amountPaise) }),
                  t("reference", { reference: issue.reference }),
                ]
                  .filter((part) => part !== null)
                  .join(" · ")}
              </p>
              {issue.resolvedAt === null ? (
                <ResolveIssue
                  id={issue.id}
                  text={{
                    open: t("resolve.open"),
                    label: t("resolve.label"),
                    confirm: t("resolve.confirm"),
                    back: t("resolve.back"),
                    need: t("resolve.need"),
                    closed: t("resolve.closed"),
                    failed: t("resolve.failed"),
                  }}
                />
              ) : (
                <p className="text-sm">
                  {t("resolved", {
                    name: issue.resolvedBy ?? t("someone"),
                    when: when(issue.resolvedAt),
                    resolution: issue.resolution ?? "",
                  })}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
