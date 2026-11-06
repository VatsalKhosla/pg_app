import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { BookingAnswer } from "@/components/owner/booking-answer";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { OWNER_BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";

// The API's limit.
const CODE_MAX_LENGTH = 32;

export async function generateMetadata({
  params,
}: PageProps<"/owner/bookings/[code]">): Promise<Metadata> {
  const { code } = await params;
  const t = await getTranslations("Owner.booking");
  return { title: t("metaTitle", { code: code.slice(0, CODE_MAX_LENGTH) }) };
}

/** A booking at one of the owner's PGs (step 7.3), with their answer while it waits for one. */
export default async function OwnerBookingPage({ params }: PageProps<"/owner/bookings/[code]">) {
  const { code } = await params;
  const path = `${OWNER_BOOKINGS_PATH}/${code}`;
  await requireOwner(path as Route);
  if (code.length > CODE_MAX_LENGTH) notFound();
  const api = await getServerApi();
  let booking;
  try {
    booking = await unwrap(api.GET("/v1/owner/bookings/{code}", { params: { path: { code } } }));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const [t, format] = await Promise.all([getTranslations("Owner.booking"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const day = (date: string) =>
    format.dateTime(new Date(`${date}T00:00:00+05:30`), { dateStyle: "medium" });
  const details = [
    { term: t("place"), value: booking.property.name },
    { term: t("roomType"), value: booking.roomType },
    { term: t("room"), value: t("roomBed", { room: booking.room, bed: booking.bed }) },
    { term: t("moveIn"), value: day(booking.moveIn) },
    { term: t("stay"), value: t("months", { months: booking.stayMonths }) },
    { term: t("rent"), value: formatINR(booking.monthlyRentPaise) },
    { term: t("token"), value: formatINR(booking.tokenPaise) },
    { term: t("dueAtMoveIn"), value: formatINR(booking.dueAtMoveInPaise) },
    { term: t("deposit"), value: formatINR(booking.depositPaise) },
    { term: t("student"), value: booking.student.name ?? t("noName") },
  ];

  return (
    <>
      <div className="space-y-2">
        <Link
          href={OWNER_BOOKINGS_PATH}
          className="inline-flex min-h-6 items-center text-sm font-semibold text-primary underline underline-offset-4 hover:text-primary-hover"
        >
          {t("back")}
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-title-1 font-semibold tracking-tight text-foreground">
            {t("title", { code: booking.code })}
          </h1>
          <span className="rounded-full border border-border/80 bg-surface px-3 py-1 text-xs font-semibold text-foreground">
            {t(`status.${booking.status}`)}
          </span>
        </div>
      </div>
      {booking.status === "token_secured" ? (
        <section className="space-y-3 rounded-2xl border border-primary/30 bg-primary-soft/60 p-5">
          {booking.confirmBy === null ? null : (
            <p className="text-sm font-medium text-foreground">
              {t("answerBy", { when: when(booking.confirmBy) })}
            </p>
          )}
          <BookingAnswer
            code={booking.code}
            text={{
              confirm: t("answer.confirm"),
              reject: t("answer.reject"),
              rejectTitle: t("answer.rejectTitle", { code: booking.code }),
              reason: t("answer.reason"),
              needReason: t("answer.needReason"),
              confirmReject: t("answer.confirmReject"),
              back: t("answer.back"),
              changed: t("answer.changed"),
              failed: t("answer.failed"),
            }}
          />
        </section>
      ) : null}
      <section
        aria-labelledby="details-title"
        className="space-y-4 rounded-2xl border border-border/80 bg-card p-5 shadow-xs sm:p-6"
      >
        <h2 id="details-title" className="text-title-3 font-semibold tracking-tight">
          {t("details")}
        </h2>
        <dl className="divide-y divide-border/80 rounded-xl border border-border/80 bg-surface/50">
          {details.map((detail) => (
            <div key={detail.term} className="grid gap-1 px-4 py-3 sm:grid-cols-3">
              <dt className="text-sm font-medium text-muted-foreground">{detail.term}</dt>
              <dd className="font-medium break-words text-foreground tabular-nums sm:col-span-2">
                {detail.value}
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}
