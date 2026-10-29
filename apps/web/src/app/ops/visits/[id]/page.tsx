import type { Metadata, Route } from "next";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { StudentVisitForms } from "@/components/ops/student-visit-forms";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { OPS_VISITS_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { formatDistance } from "@/lib/format/distance";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.studentVisits.detail");
  return { title: t("metaTitle") };
}

/**
 * One student's visit (step 3.7): the student and the PG, booking it, and its log: when it was
 * asked for and booked, when and where the agent checked in, and how it went.
 */
export default async function OpsVisitPage({ params }: PageProps<"/ops/visits/[id]">) {
  const { id } = await params;
  await requireOps(`${OPS_VISITS_PATH}/${id}` as Route);
  if (!UUID.test(id)) notFound();
  const api = await getServerApi();
  let visit;
  try {
    visit = await unwrap(
      api.GET("/v1/ops/visits/{visit_id}", { params: { path: { visit_id: id } } }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const agents = await unwrap(api.GET("/v1/ops/field-agents"));
  const t = await getTranslations("Ops.studentVisits");
  const format = await getFormatter();
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const log = [
    t("detail.logRequested", { count: visit.preferredStarts.length }) +
      ` · ${when(visit.requestedAt)}`,
    ...(visit.scheduledAt === null
      ? []
      : [t("detail.logScheduled", { when: when(visit.scheduledAt) })]),
    ...(visit.checkIn === null
      ? []
      : [
          t("detail.logCheckedIn", {
            when: when(visit.checkIn.at),
            distance: formatDistance(visit.checkIn.distanceM),
            accuracy: formatDistance(visit.checkIn.accuracyM),
          }),
        ]),
    ...(visit.finishedAt === null || visit.outcome === null
      ? []
      : [
          t("detail.logFinished", {
            when: when(visit.finishedAt),
            outcome: t(`outcome.${visit.outcome}`),
          }),
        ]),
    ...(visit.cancelledAt === null || visit.cancelledBy === null
      ? []
      : [
          t("detail.logCancelled", {
            when: when(visit.cancelledAt),
            by: t(`detail.by.${visit.cancelledBy}`),
          }),
        ]),
  ];

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{visit.property.name}</h1>
        <p className="text-muted-foreground">
          {t(`status.${visit.status}`)} · {visit.property.addressLine}, {visit.property.locality}
        </p>
      </div>
      <section aria-labelledby="student-title" className="space-y-1">
        <h2 id="student-title" className="text-lg font-semibold">
          {t("student")}
        </h2>
        <p>{visit.student.name ?? visit.student.phone}</p>
        <a href={`tel:${visit.student.phone}`} className="text-sm underline underline-offset-4">
          {t("detail.call", { phone: visit.student.phone })}
        </a>
      </section>
      <StudentVisitForms
        id={visit.id}
        offered={visit.preferredStarts.map((start) => ({ value: start, label: when(start) }))}
        agents={agents.items.map((agent) => ({ id: agent.id, name: agent.name ?? agent.id }))}
        booked={visit.scheduledAt !== null}
        open={
          visit.status === "requested" || (visit.status === "scheduled" && visit.checkIn === null)
        }
      />
      <section aria-labelledby="log-title" className="space-y-2">
        <h2 id="log-title" className="text-lg font-semibold">
          {t("detail.log")}
        </h2>
        <ol className="list-decimal space-y-1 ps-5 text-sm">
          {log.map((entry) => (
            <li key={entry}>{entry}</li>
          ))}
        </ol>
        {visit.outcomeNote === "" ? null : (
          <p className="text-sm">{t("detail.note", { note: visit.outcomeNote })}</p>
        )}
      </section>
    </div>
  );
}
