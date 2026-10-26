import "server-only";

import type { Schemas } from "@pg-platform/api-client";
import { getFormatter, getTranslations } from "next-intl/server";

import { VisitReport } from "@/components/field/visit-report";

import { CancelVisit } from "./cancel-visit";

type Visit = Schemas["VisitInfo"];

/** A listing's verification visits, newest first: booked ones can be cancelled, and reported
 * ones show their report. */
export async function VisitList({ visits }: { visits: Visit[] }) {
  const t = await getTranslations("Ops.visits");
  const format = await getFormatter();
  if (visits.length === 0) return <p className="text-sm text-muted-foreground">{t("empty")}</p>;

  return (
    <ol className="space-y-3">
      {visits.map((visit) => (
        <li key={visit.id} className="space-y-3 rounded-md border p-3">
          <p className="text-sm">
            <span className="font-medium">{t(`status.${visit.status}`)}</span>
            {" · "}
            {format.dateTime(new Date(visit.scheduledFor), {
              dateStyle: "medium",
              timeStyle: "short",
            })}
            {" · "}
            {visit.agent?.name ?? t("unnamed")}
          </p>
          {visit.status === "scheduled" ? <CancelVisit visitId={visit.id} /> : null}
          {visit.status === "cancelled" ? (
            <p className="text-sm text-muted-foreground">
              {t("cancelledBecause", { reason: visit.cancelReason ?? "" })}
            </p>
          ) : null}
          {visit.status === "submitted" ? (
            <details>
              <summary className="cursor-pointer text-sm font-medium">{t("report")}</summary>
              <div className="pt-3">
                <VisitReport visit={visit} />
              </div>
            </details>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
