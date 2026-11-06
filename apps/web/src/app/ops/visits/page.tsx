import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_VISITS_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

const STATUSES = ["requested", "scheduled", "completed", "no_show", "cancelled"] as const;
type Status = (typeof STATUSES)[number];

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.studentVisits");
  return { title: t("metaTitle") };
}

/** Students' visits (step 3.7): newest first, of one status if chosen, each with its PG and times. */
export default async function OpsVisitsPage({ searchParams }: PageProps<"/ops/visits">) {
  await requireOps(OPS_VISITS_PATH);
  const asked = (await searchParams).status;
  const status = STATUSES.find((each) => each === asked);
  const api = await getServerApi();
  const page = await unwrap(
    api.GET("/v1/ops/visits", { params: { query: { status, limit: 50 } } }),
  );
  const t = await getTranslations("Ops.studentVisits");
  const format = await getFormatter();
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const filters: { label: string; status: Status | undefined }[] = [
    { label: t("all"), status: undefined },
    ...STATUSES.map((each) => ({ label: t(`status.${each}`), status: each })),
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-title-1 text-foreground">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <nav aria-label={t("filter")} className="flex flex-wrap gap-2">
        {filters.map((filter) => (
          <Link
            key={filter.label}
            href={
              (filter.status === undefined
                ? OPS_VISITS_PATH
                : `${OPS_VISITS_PATH}?status=${filter.status}`) as Route
            }
            aria-current={filter.status === status ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-full border border-border/80 bg-card px-3.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors outline-none hover:bg-surface hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50",
              filter.status === status &&
                "border-primary bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
            )}
          >
            {filter.label}
          </Link>
        ))}
      </nav>
      {page.items.length === 0 ? (
        <p className="text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="divide-y divide-border/60 rounded-2xl border border-border/80 bg-card shadow-xs">
          {page.items.map((visit) => (
            <li key={visit.id} className="space-y-1 p-4">
              <Link
                href={`${OPS_VISITS_PATH}/${visit.id}` as Route}
                className="font-semibold text-primary underline-offset-4 hover:underline"
              >
                {visit.property.name}
              </Link>
              <p className="text-sm text-muted-foreground">
                {t(`status.${visit.status}`)} · {visit.student.name ?? visit.student.phone}
              </p>
              <p className="text-sm tabular-nums">
                {visit.scheduledAt === null || visit.agent === null
                  ? `${t("offered")}: ${visit.preferredStarts.map(when).join(", ")}`
                  : t("booked", {
                      when: when(visit.scheduledAt),
                      agent: visit.agent.name ?? visit.agent.phone,
                    })}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
