import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { FIELD_VISITS_PATH } from "@/lib/auth/routes";
import { requireFieldStaff } from "@/lib/auth/session";

type Visit = Schemas["VisitInfo"];

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Field.visits");
  return { title: t("title") };
}

/** A field agent's visits: those booked, soonest first, and those reported on. */
export default async function FieldVisitsPage() {
  await requireFieldStaff(FIELD_VISITS_PATH);
  const api = await getServerApi();
  const [booked, done] = await Promise.all([
    unwrap(
      api.GET("/v1/ops/verification-visits", {
        params: { query: { status: "scheduled", limit: 50 } },
      }),
    ),
    unwrap(
      api.GET("/v1/ops/verification-visits", {
        params: { query: { status: "submitted", limit: 20 } },
      }),
    ),
  ]);
  const t = await getTranslations("Field.visits");
  const format = await getFormatter();

  function item(visit: Visit) {
    return (
      <li key={visit.id}>
        <Link
          href={`/field/visits/${visit.id}` as Route}
          className="block space-y-1 p-3 hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <span className="block font-medium">{visit.property.name}</span>
          <span className="block text-sm text-muted-foreground">
            {visit.property.locality.name} · {visit.property.addressLine}
          </span>
          <span className="block text-sm">
            {format.dateTime(new Date(visit.scheduledFor), {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </span>
        </Link>
      </li>
    );
  }

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <section aria-labelledby="booked-title" className="space-y-3">
        <h2 id="booked-title" className="text-lg font-semibold">
          {t("booked")}
        </h2>
        {booked.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noneBooked")}</p>
        ) : (
          <ul className="divide-y rounded-md border">{booked.items.map(item)}</ul>
        )}
      </section>
      {done.items.length === 0 ? null : (
        <section aria-labelledby="done-title" className="space-y-3">
          <h2 id="done-title" className="text-lg font-semibold">
            {t("done")}
          </h2>
          <ul className="divide-y rounded-md border">{done.items.map(item)}</ul>
        </section>
      )}
    </div>
  );
}
