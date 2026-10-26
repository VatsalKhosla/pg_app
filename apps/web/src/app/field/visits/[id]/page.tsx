import type { Metadata, Route } from "next";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { ReportForm } from "@/components/field/report-form";
import { VisitReport } from "@/components/field/visit-report";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { requireFieldStaff } from "@/lib/auth/session";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Field.visit");
  return { title: t("metaTitle") };
}

/** Directions to the building in the phone's maps (Google's public Maps URLs: no key). */
function directions(lat: number, lng: number): string {
  const query = new URLSearchParams({ api: "1", destination: `${String(lat)},${String(lng)}` });
  return `https://www.google.com/maps/dir/?${query.toString()}`;
}

/**
 * One visit: where to go and whom to call, then the report form while it's booked for this agent,
 * or the report once it's in.
 */
export default async function FieldVisitPage({ params }: PageProps<"/field/visits/[id]">) {
  const { id } = await params;
  const me = await requireFieldStaff(`/field/visits/${id}` as Route);
  if (!UUID.test(id)) notFound();
  const api = await getServerApi();
  let visit;
  try {
    visit = await unwrap(
      api.GET("/v1/ops/verification-visits/{visit_id}", { params: { path: { visit_id: id } } }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const t = await getTranslations("Field.visit");
  const format = await getFormatter();
  const place = visit.property;
  const mine = visit.agent?.id === me.id;

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{place.name}</h1>
        <p className="text-muted-foreground">
          {t(`status.${visit.status}`)}
          {" · "}
          {format.dateTime(new Date(visit.scheduledFor), {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </p>
      </div>

      <section aria-labelledby="where-title" className="space-y-2">
        <h2 id="where-title" className="text-lg font-semibold">
          {t("where")}
        </h2>
        <p>
          {place.addressLine}
          <span className="text-muted-foreground"> · {place.locality.name}</span>
        </p>
        <p className="text-sm">
          <a
            href={directions(place.location.lat, place.location.lng)}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-primary underline underline-offset-4"
          >
            {t("directions")}
          </a>
        </p>
        <p className="text-sm">
          {t("owner", { business: place.ownerBusinessName })}
          {place.ownerPhone === null ? null : (
            <>
              {" · "}
              <a
                href={`tel:${place.ownerPhone}`}
                className="font-medium text-primary underline underline-offset-4"
              >
                {place.ownerPhone}
              </a>
            </>
          )}
        </p>
      </section>

      <section aria-labelledby="report-title" className="space-y-4">
        <h2 id="report-title" className="text-lg font-semibold">
          {t("report")}
        </h2>
        {visit.status === "submitted" ? <VisitReport visit={visit} /> : null}
        {visit.status === "cancelled" ? (
          <p className="text-sm">{t("cancelled", { reason: visit.cancelReason ?? "" })}</p>
        ) : null}
        {visit.status === "scheduled" && mine ? <ReportForm visit={visit} /> : null}
        {visit.status === "scheduled" && !mine ? (
          <p className="text-sm text-muted-foreground">
            {t("bookedFor", { name: visit.agent?.name ?? t("anAgent") })}
          </p>
        ) : null}
      </section>
    </div>
  );
}
