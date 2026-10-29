import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { VisitRequestForm } from "@/components/visits/visit-request-form";
import { getPublicListing } from "@/lib/api/public";
import { OPS_VISITS_PATH } from "@/lib/auth/routes";
import { isStaff, requireSession } from "@/lib/auth/session";
import { visitDays, visitTimes } from "@/lib/visits/times";

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/u;
const CHOICES = 3;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Pg.visit");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/**
 * Asking to visit a PG (step 3.7, ADR 0033): signed in by phone, a student offers up to three
 * times; ops call to book one with a field agent. Staff book visits from the ops console instead.
 */
export default async function VisitPage({ params }: PageProps<"/pg/[slug]/visit">) {
  const { slug } = await params;
  if (!SLUG.test(slug) || slug.length > 80) notFound();
  const me = await requireSession(`/pg/${slug}/visit` as Route);
  const listing = await getPublicListing(slug);
  if (listing === null) notFound();
  const t = await getTranslations("Pg.visit");
  const format = await getFormatter();
  const days = visitDays(new Date()).map((day) => ({
    value: day,
    label: format.dateTime(new Date(`${day}T12:00:00+05:30`), {
      weekday: "short",
      day: "numeric",
      month: "short",
    }),
  }));
  const times = visitTimes().map((time) => ({
    value: time,
    label: format.dateTime(new Date(`2000-01-01T${time}:00+05:30`), {
      hour: "numeric",
      minute: "2-digit",
    }),
  }));

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 px-4 py-10 sm:py-16">
      <div className="space-y-3">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
          {t("title", { name: listing.name })}
        </h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {isStaff(me) ? (
        <Link
          href={OPS_VISITS_PATH}
          className="inline-flex min-h-6 items-center font-medium text-primary underline underline-offset-4"
        >
          {OPS_VISITS_PATH}
        </Link>
      ) : (
        <VisitRequestForm
          slug={slug}
          days={days}
          times={times}
          text={{
            slots: Array.from({ length: CHOICES }, (_, index) =>
              index === 0
                ? t("slot", { number: index + 1 })
                : `${t("slot", { number: index + 1 })} ${t("optional")}`,
            ),
            day: t("day"),
            time: t("time"),
            chooseDay: t("chooseDay"),
            chooseTime: t("chooseTime"),
            needOne: t("needOne"),
            needBoth: t("needBoth"),
            submit: t("submit"),
            submitting: t("submitting"),
            errors: {
              VISIT_EXISTS: t("errors.VISIT_EXISTS"),
              VISIT_LIMIT_REACHED: t("errors.VISIT_LIMIT_REACHED"),
              RATE_LIMITED: t("errors.RATE_LIMITED"),
              generic: t("errors.generic"),
            },
          }}
        />
      )}
      <Link
        href={`/pg/${slug}` as Route}
        className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
      >
        {t("back")}
      </Link>
    </div>
  );
}
