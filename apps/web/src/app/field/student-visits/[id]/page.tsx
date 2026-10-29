import type { Metadata, Route } from "next";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { StudentVisitActions } from "@/components/field/student-visit-actions";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { FIELD_STUDENT_VISITS_PATH } from "@/lib/auth/routes";
import { requireFieldStaff } from "@/lib/auth/session";
import { formatDistance } from "@/lib/format/distance";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Field.studentVisits.detail");
  return { title: t("metaTitle") };
}

/** Directions to the building in the phone's maps (Google's public Maps URLs: no key). */
function directions(lat: number, lng: number): string {
  const query = new URLSearchParams({ api: "1", destination: `${String(lat)},${String(lng)}` });
  return `https://www.google.com/maps/dir/?${query.toString()}`;
}

/**
 * A student's visit, for the agent running it (step 3.7): where and when, whom to call, then
 * checking in and saying how it went.
 */
export default async function StudentVisitPage({
  params,
}: PageProps<"/field/student-visits/[id]">) {
  const { id } = await params;
  await requireFieldStaff(`${FIELD_STUDENT_VISITS_PATH}/${id}` as Route);
  if (!UUID.test(id)) notFound();
  const api = await getServerApi();
  let visit;
  try {
    visit = await unwrap(
      api.GET("/v1/field/visits/{visit_id}", { params: { path: { visit_id: id } } }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const t = await getTranslations("Field.studentVisits");
  const format = await getFormatter();
  const place = visit.property;
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{place.name}</h1>
        {visit.scheduledAt === null ? null : (
          <p className="text-muted-foreground">{when(visit.scheduledAt)}</p>
        )}
      </div>
      <section aria-labelledby="where-title" className="space-y-1">
        <h2 id="where-title" className="text-lg font-semibold">
          {t("detail.where")}
        </h2>
        <p>
          {place.addressLine}
          <span className="text-muted-foreground"> · {place.locality}</span>
        </p>
        <a
          href={directions(place.location.lat, place.location.lng)}
          className="text-sm underline underline-offset-4"
        >
          {t("detail.directions")}
        </a>
      </section>
      <section aria-labelledby="student-title" className="space-y-1">
        <h2 id="student-title" className="text-lg font-semibold">
          {t("detail.student")}
        </h2>
        <a href={`tel:${visit.student.phone}`} className="underline underline-offset-4">
          {t("detail.call", { name: visit.student.name ?? visit.student.phone })}
        </a>
      </section>
      {visit.checkIn === null ? null : (
        <p className="text-sm">
          {t("detail.checkedIn", {
            when: when(visit.checkIn.at),
            distance: formatDistance(visit.checkIn.distanceM),
          })}
        </p>
      )}
      {visit.status === "scheduled" ? (
        <StudentVisitActions id={visit.id} checkedIn={visit.checkIn !== null} />
      ) : visit.outcome === null ? null : (
        <p className="font-medium">{t("detail.done", { outcome: t(`detail.${visit.outcome}`) })}</p>
      )}
    </div>
  );
}
