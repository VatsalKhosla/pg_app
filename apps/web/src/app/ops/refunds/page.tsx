import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { RefundAnswer } from "@/components/ops/refund-answer";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_BOOKINGS_PATH, OPS_REFUNDS_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";
import { cn } from "@/lib/utils";

type Status = Schemas["OpsRefund"]["status"];

const STATUSES = [
  "awaiting_approval",
  "failed",
  "requested",
  "pending",
  "processed",
  "declined",
] as const satisfies readonly Status[];

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.refunds");
  return { title: t("metaTitle") };
}

/**
 * Refunds (step 6.3, ADR 0059): a queue, oldest first, opening on those waiting for a second
 * person. Each links to its booking, where ops also start one.
 */
export default async function OpsRefundsPage({ searchParams }: PageProps<"/ops/refunds">) {
  await requireOps(OPS_REFUNDS_PATH);
  const asked = (await searchParams).status;
  const status: Status = STATUSES.find((each) => each === asked) ?? "awaiting_approval";
  const api = await getServerApi();
  const page = await unwrap(
    api.GET("/v1/ops/refunds", { params: { query: { status, limit: 50 } } }),
  );
  const [t, format] = await Promise.all([getTranslations("Ops.refunds"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-title-1 text-foreground">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <nav aria-label={t("statusFilter")} className="flex flex-wrap gap-2">
        {STATUSES.map((each) => (
          <Link
            key={each}
            href={`${OPS_REFUNDS_PATH}?status=${each}` as Route}
            aria-current={each === status ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-full border border-border/80 bg-card px-3.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors outline-none hover:bg-surface hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
              each === status &&
                "border-primary bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
            )}
          >
            {t(`status.${each}`)}
          </Link>
        ))}
      </nav>
      {page.items.length === 0 ? (
        <p className="text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="space-y-4">
          {page.items.map((refund) => (
            <li
              key={refund.id}
              className="space-y-2 rounded-2xl border border-border/80 bg-card p-5 shadow-xs"
            >
              <p className="font-semibold text-foreground tabular-nums">
                {t("line", { amount: formatINR(refund.amountPaise), code: refund.booking })}
              </p>
              <p>{refund.reason}</p>
              <p className="text-sm text-muted-foreground">
                {t("asked", {
                  who: refund.requestedBy ?? t("nobody"),
                  when: when(refund.requestedAt),
                })}
              </p>
              {refund.failure === null ? null : (
                <p className="text-sm text-destructive">{refund.failure}</p>
              )}
              <Link
                href={`${OPS_BOOKINGS_PATH}/${refund.booking}` as Route}
                className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
              >
                {t("open", { code: refund.booking })}
              </Link>
              {refund.status === "awaiting_approval" ? (
                <RefundAnswer
                  id={refund.id}
                  text={{
                    approve: t("answer.approve"),
                    decline: t("answer.decline"),
                    declineTitle: t("answer.declineTitle", {
                      amount: formatINR(refund.amountPaise),
                    }),
                    reason: t("answer.reason"),
                    needReason: t("answer.needReason"),
                    confirmDecline: t("answer.confirmDecline"),
                    back: t("answer.back"),
                    secondPerson: t("answer.secondPerson"),
                    answered: t("answer.answered"),
                    failed: t("answer.failed"),
                  }}
                />
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
