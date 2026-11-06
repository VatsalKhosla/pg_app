import { ArrowLeft } from "lucide-react";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { ArchWatermark } from "@/components/brand/editorial-art";
import { Card } from "@/components/ui/card";
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
    <div className="mx-auto w-full max-w-2xl space-y-6 px-gutter py-10 sm:py-16">
      <div className="relative space-y-3 overflow-hidden rounded-3xl border border-saffron-border bg-surface-warm p-6 shadow-xs sm:p-8">
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-1.5"
          style={{
            backgroundImage:
              "linear-gradient(90deg, var(--primary) 0%, var(--sage) 35%, var(--saffron) 70%, var(--coral) 100%)",
          }}
        />
        <ArchWatermark tone="saffron" className="absolute -right-6 -bottom-6 size-36 opacity-15" />
        <Link
          href={`/pg/${slug}` as Route}
          className="relative inline-flex min-h-8 items-center gap-1.5 text-sm font-semibold text-primary underline underline-offset-4"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          {t("back")}
        </Link>
        <h1 className="relative text-title-1 font-bold text-foreground">
          {t("title", { name: listing.name })}
        </h1>
        <p className="relative text-muted-foreground">{t("intro")}</p>
      </div>
      {isStaff(me) ? (
        <Card className="p-6">
          <Link
            href={OPS_VISITS_PATH}
            className="inline-flex min-h-8 items-center font-medium text-primary underline underline-offset-4"
          >
            {OPS_VISITS_PATH}
          </Link>
        </Card>
      ) : (
        <Card className="rounded-3xl p-6 shadow-sm sm:p-8">
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
        </Card>
      )}
    </div>
  );
}
