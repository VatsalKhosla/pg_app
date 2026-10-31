import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_DISPUTES_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

const STATUSES = ["open", "resolved_refund", "resolved_uphold"] as const;
type Status = (typeof STATUSES)[number];
const ALL = "all";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.disputes");
  return { title: t("metaTitle") };
}

/**
 * Students' reports that their room isn't as shown (step 5.7, ADR 0051): a queue, oldest first,
 * the open ones unless another status is chosen. Each one's booking waits until ops settle it.
 */
export default async function OpsDisputesPage({ searchParams }: PageProps<"/ops/disputes">) {
  await requireOps(OPS_DISPUTES_PATH);
  const asked = (await searchParams).status;
  const status: Status | typeof ALL =
    asked === ALL ? ALL : (STATUSES.find((each) => each === asked) ?? "open");
  const api = await getServerApi();
  const page = await unwrap(
    api.GET("/v1/ops/disputes", {
      params: { query: { status: status === ALL ? undefined : status, limit: 50 } },
    }),
  );
  const [t, format] = await Promise.all([getTranslations("Ops.disputes"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const filters: { label: string; status: Status | typeof ALL }[] = [
    ...STATUSES.map((each) => ({ label: t(`status.${each}`), status: each })),
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
            href={`${OPS_DISPUTES_PATH}?status=${filter.status}` as Route}
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
          {page.items.map((dispute) => (
            <li key={dispute.id} className="space-y-1 p-4">
              <p>
                <Link
                  href={`${OPS_DISPUTES_PATH}/${dispute.id}` as Route}
                  className="font-semibold underline-offset-4 hover:underline"
                >
                  {t("item", { code: dispute.booking, pg: dispute.property.name })}
                </Link>
              </p>
              <p className="text-sm text-muted-foreground">
                {t(`status.${dispute.status}`)} · {t(`reasons.${dispute.reason}`)} ·{" "}
                {dispute.property.locality} · {t("photoCount", { count: dispute.photos })}
              </p>
              <p className="text-sm">{t("openedOn", { when: when(dispute.openedAt) })}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
