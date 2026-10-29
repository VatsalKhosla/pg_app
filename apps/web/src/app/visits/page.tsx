import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { buttonVariants } from "@/components/ui/button";
import { CancelMyVisit } from "@/components/visits/cancel-my-visit";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { VISITS_PATH } from "@/lib/auth/routes";
import { requireSession } from "@/lib/auth/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Visits");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

const OPEN = ["requested", "scheduled"];
const ENTITLING = ["scheduled", "completed", "no_show"];

/**
 * A student's visits (step 3.7, ADR 0033): asked for, booked, done or cancelled. A booked visit
 * shows the PG's address and the owner's phone, which only then may the student see (CLAUDE.md
 * rule 11); each look at them is in the API's audit log.
 */
export default async function VisitsPage() {
  await requireSession(VISITS_PATH);
  const api = await getServerApi();
  const { items } = await unwrap(api.GET("/v1/visits"));
  const t = await getTranslations("Visits");
  const format = await getFormatter();
  const contacts = new Map(
    await Promise.all(
      items
        .filter((visit) => ENTITLING.includes(visit.status))
        .map(async (visit) => {
          try {
            const contact = await unwrap(
              api.GET("/v1/properties/{slug}/contact", {
                params: { path: { slug: visit.property.slug } },
              }),
            );
            return [visit.id, contact] as const;
          } catch (error) {
            if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
              return [visit.id, null] as const;
            }
            throw error;
          }
        }),
    ),
  );
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });

  return (
    <div className="mx-auto w-full max-w-2xl space-y-8 px-4 py-10 sm:py-16">
      <div className="space-y-3">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {items.length === 0 ? (
        <div className="space-y-4 rounded-lg border border-dashed p-6">
          <p>{t("none")}</p>
          <Link href="/search" className={buttonVariants()}>
            {t("find")}
          </Link>
        </div>
      ) : (
        <ul className="space-y-4">
          {items.map((visit) => {
            const contact = contacts.get(visit.id);
            return (
              <li key={visit.id} className="space-y-3 rounded-lg border p-4">
                <div className="space-y-1">
                  <Link
                    href={`/pg/${visit.property.slug}` as Route}
                    className="font-semibold underline-offset-4 hover:underline"
                  >
                    {visit.property.name}
                  </Link>
                  <p className="text-sm text-muted-foreground">
                    {visit.property.locality} · {t(`status.${visit.status}`)}
                  </p>
                </div>
                {visit.scheduledAt === null ? (
                  <div className="text-sm">
                    <p className="font-medium">{t("offered")}</p>
                    <ul className="list-disc ps-5">
                      {visit.preferredStarts.map((start) => (
                        <li key={start}>{when(start)}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="space-y-1 text-sm">
                    <p className="font-medium">{t("booked", { when: when(visit.scheduledAt) })}</p>
                    {visit.agentName === null ? null : (
                      <p>{t("agent", { name: visit.agentName })}</p>
                    )}
                  </div>
                )}
                {contact == null ? null : (
                  <dl className="grid gap-1 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-4">
                    <dt className="text-muted-foreground">{t("address")}</dt>
                    <dd>{contact.addressLine}</dd>
                    {contact.ownerPhone === null ? null : (
                      <>
                        <dt className="text-muted-foreground">{t("ownerPhone")}</dt>
                        <dd>
                          <a
                            href={`tel:${contact.ownerPhone}`}
                            className="underline underline-offset-4"
                          >
                            {contact.ownerPhone}
                          </a>
                        </dd>
                      </>
                    )}
                  </dl>
                )}
                {visit.status === "cancelled" ? (
                  <p className="text-sm text-muted-foreground">
                    {visit.cancelledBy === "student"
                      ? t("cancelledByStudent")
                      : t("cancelledByOps")}
                  </p>
                ) : null}
                {OPEN.includes(visit.status) ? (
                  <CancelMyVisit
                    id={visit.id}
                    text={{ cancel: t("cancel"), cancelling: t("cancelling"), failed: t("failed") }}
                  />
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
