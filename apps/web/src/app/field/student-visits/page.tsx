import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { FIELD_STUDENT_VISITS_PATH } from "@/lib/auth/routes";
import { requireFieldStaff } from "@/lib/auth/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Field.studentVisits");
  return { title: t("metaTitle") };
}

/** The student visits booked for this agent (step 3.7), from yesterday on, soonest first. */
export default async function StudentVisitsPage() {
  await requireFieldStaff(FIELD_STUDENT_VISITS_PATH);
  const api = await getServerApi();
  const { items } = await unwrap(api.GET("/v1/field/visits"));
  const t = await getTranslations("Field.studentVisits");
  const format = await getFormatter();

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {items.length === 0 ? (
        <p className="text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {items.map((visit) => (
            <li key={visit.id} className="space-y-1 p-4">
              <Link
                href={`${FIELD_STUDENT_VISITS_PATH}/${visit.id}` as Route}
                className="font-semibold underline-offset-4 hover:underline"
              >
                {visit.property.name}
              </Link>
              <p className="text-sm text-muted-foreground">
                {visit.scheduledAt === null
                  ? null
                  : format.dateTime(new Date(visit.scheduledAt), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                {visit.status === "scheduled" ||
                visit.status === "completed" ||
                visit.status === "no_show"
                  ? ` · ${t(`status.${visit.status}`)}`
                  : null}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
