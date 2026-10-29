import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_GRIEVANCES_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

const STATUSES = ["received", "acknowledged", "resolved"] as const;
type Status = (typeof STATUSES)[number];
const ALL = "all";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.grievances");
  return { title: t("metaTitle") };
}

/**
 * The grievance queue (step 3.8, ADR 0034): oldest first, the order they fall due, the ones
 * waiting for an acknowledgement unless another status is chosen. A missed deadline is marked.
 */
export default async function OpsGrievancesPage({ searchParams }: PageProps<"/ops/grievances">) {
  await requireOps(OPS_GRIEVANCES_PATH);
  const asked = (await searchParams).status;
  const status: Status | typeof ALL =
    asked === ALL ? ALL : (STATUSES.find((each) => each === asked) ?? "received");
  const api = await getServerApi();
  const page = await unwrap(
    api.GET("/v1/ops/grievances", {
      params: { query: { status: status === ALL ? undefined : status, limit: 50 } },
    }),
  );
  const [t, tGrievances, format] = await Promise.all([
    getTranslations("Ops.grievances"),
    getTranslations("Grievances"),
    getFormatter(),
  ]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const filters: { label: string; status: Status | typeof ALL }[] = [
    ...STATUSES.map((each) => ({ label: tGrievances(`status.${each}`), status: each })),
    { label: t("all"), status: ALL },
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <nav aria-label={t("statusFilter")} className="flex flex-wrap gap-2">
        {filters.map((filter) => (
          <Link
            key={filter.status}
            href={`${OPS_GRIEVANCES_PATH}?status=${filter.status}` as Route}
            aria-current={filter.status === status ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-full border px-3 text-sm outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50",
              filter.status === status && "border-primary bg-accent font-medium",
            )}
          >
            {filter.label}
          </Link>
        ))}
      </nav>
      {page.items.length === 0 ? (
        <p className="text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {page.items.map((grievance) => (
            <li key={grievance.ticketNumber} className="space-y-1 p-4">
              <p className="flex flex-wrap items-center gap-2">
                <Link
                  href={`${OPS_GRIEVANCES_PATH}/${grievance.ticketNumber}` as Route}
                  className="font-mono font-semibold underline-offset-4 hover:underline"
                >
                  {grievance.ticketNumber}
                </Link>
                {grievance.late ? (
                  <span className="rounded-full border border-destructive px-2 py-0.5 text-xs font-semibold text-destructive">
                    {t("late")}
                  </span>
                ) : null}
              </p>
              <p className="text-sm text-muted-foreground">
                {tGrievances(`status.${grievance.status}`)} ·{" "}
                {tGrievances(`categories.${grievance.category}`)} ·{" "}
                {grievance.complainant.name === "" ? t("noName") : grievance.complainant.name}
              </p>
              <p className="text-sm">
                {t("receivedOn", { when: when(grievance.receivedAt) })}
                {grievance.status === "received"
                  ? ` · ${t("acknowledgeBy", { when: when(grievance.acknowledgeBy) })}`
                  : grievance.status === "acknowledged"
                    ? ` · ${t("resolveBy", { when: when(grievance.resolveBy) })}`
                    : null}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
