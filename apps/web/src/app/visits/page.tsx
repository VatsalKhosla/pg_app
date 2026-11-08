import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { ArchWatermark } from "@/components/brand/editorial-art";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CancelMyVisit } from "@/components/visits/cancel-my-visit";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { BOOKINGS_PATH, VISITS_PATH } from "@/lib/auth/routes";
import { requireSession } from "@/lib/auth/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Visits");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

const visitBars = ["bg-primary", "bg-marigold", "bg-neem", "bg-dusk"] as const;
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
    <div className="mx-auto w-full max-w-3xl space-y-8 px-gutter py-10 sm:py-16">
      <div className="relative space-y-2.5 overflow-hidden rounded-3xl border border-marigold-border bg-surface-warm p-6 shadow-xs sm:p-8">
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-1.5"
          style={{
            backgroundImage:
              "linear-gradient(90deg, var(--primary) 0%, var(--neem) 35%, var(--marigold) 70%, var(--ember) 100%)",
          }}
        />
        <ArchWatermark tone="neem" className="absolute -right-6 -bottom-6 size-40 opacity-15" />
        <h1 className="relative text-title-1 font-bold tracking-tight text-foreground">
          {t("title")}
        </h1>
        <p className="relative text-body text-muted-foreground">{t("intro")}</p>
      </div>
      {items.length === 0 ? (
        <Card variant="warm" className="space-y-4 rounded-3xl border-dashed p-6">
          <p className="text-body text-muted-foreground">{t("none")}</p>
          <Link href="/search" className={buttonVariants({ shape: "pill" })}>
            {t("find")}
          </Link>
        </Card>
      ) : (
        <ul className="space-y-4">
          {items.map((visit, index) => {
            const contact = contacts.get(visit.id);
            return (
              <li
                key={visit.id}
                className="relative space-y-4 overflow-hidden rounded-2xl border border-border/80 bg-card p-5 shadow-xs transition-shadow hover:shadow-sm sm:p-6"
              >
                <span
                  aria-hidden="true"
                  className={`absolute inset-x-0 top-0 h-1.5 ${visitBars[index % visitBars.length] ?? "bg-primary"}`}
                />
                <div className="space-y-1 pt-1">
                  <Link
                    href={`/pg/${visit.property.slug}` as Route}
                    className="text-title-3 font-semibold text-foreground underline-offset-4 hover:text-primary hover:underline"
                  >
                    {visit.property.name}
                  </Link>
                  <p className="text-body-sm text-muted-foreground">
                    {visit.property.locality} ·{" "}
                    <span className="font-medium text-foreground">
                      {t(`status.${visit.status}`)}
                    </span>
                  </p>
                </div>
                {visit.scheduledAt === null ? (
                  <div className="space-y-1.5 rounded-xl border border-marigold-border bg-marigold-soft p-3.5 text-sm">
                    <p className="font-semibold text-marigold-soft-foreground">{t("offered")}</p>
                    <ul className="list-disc space-y-1 ps-5 text-foreground">
                      {visit.preferredStarts.map((start) => (
                        <li key={start}>{when(start)}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="space-y-1 rounded-xl border border-neem-border bg-neem-soft p-3.5 text-sm">
                    <p className="font-semibold text-neem-soft-foreground">
                      {t("booked", { when: when(visit.scheduledAt) })}
                    </p>
                    {visit.agentName === null ? null : (
                      <p className="text-foreground">{t("agent", { name: visit.agentName })}</p>
                    )}
                  </div>
                )}
                {contact == null ? null : (
                  <dl className="grid gap-1.5 rounded-xl border border-marigold-border/70 bg-surface-warm p-3.5 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-4">
                    <dt className="font-medium text-muted-foreground">{t("address")}</dt>
                    <dd className="text-foreground">{contact.addressLine}</dd>
                    {contact.ownerPhone === null ? null : (
                      <>
                        <dt className="font-medium text-muted-foreground">{t("ownerPhone")}</dt>
                        <dd>
                          <a
                            href={`tel:${contact.ownerPhone}`}
                            className="font-mono font-medium text-primary underline underline-offset-4 hover:text-primary-hover"
                          >
                            {contact.ownerPhone}
                          </a>
                        </dd>
                      </>
                    )}
                  </dl>
                )}
                {visit.booking === null ? null : (
                  <p className="text-sm">
                    <Link
                      href={`${BOOKINGS_PATH}/${visit.booking}` as Route}
                      className="font-semibold text-primary underline underline-offset-4 hover:text-primary-hover"
                    >
                      {t("reserved", { code: visit.booking })}
                    </Link>
                  </p>
                )}
                {visit.canReserve ? (
                  <div className="space-y-2.5 rounded-xl border border-primary-border bg-primary-soft p-4">
                    <p className="text-sm font-medium text-foreground">{t("reserveHint")}</p>
                    <Link
                      href={`/pg/${visit.property.slug}?visit=${visit.id}#quote-title` as Route}
                      className={buttonVariants({ shape: "pill" })}
                    >
                      {t("reserve")}
                    </Link>
                  </div>
                ) : null}
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
