import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { BookingActions } from "@/components/bookings/booking-actions";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireSession } from "@/lib/auth/session";
import { actionsFor } from "@/lib/bookings/actions";
import { dayText } from "@/lib/format/days";
import { formatINR } from "@/lib/money";
import { trustPages } from "@/lib/trust/pages";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Bookings");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

type Contact = Schemas["ListingContact"];

/**
 * A student's booking (step 5.5, ADR 0049): what happens next, what they pay and to whom, where
 * to go once the owner confirms (the address and the owner's phone show only then; CLAUDE.md
 * rule 11), what happened so far, and cancelling, with what it gives back shown first.
 */
export default async function BookingPage({ params }: PageProps<"/bookings/[code]">) {
  const { code } = await params;
  await requireSession(`${BOOKINGS_PATH}/${code}` as Route);
  const api = await getServerApi();
  let booking: Schemas["StudentBooking"];
  try {
    booking = await unwrap(api.GET("/v1/bookings/{code}", { params: { path: { code } } }));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const t = await getTranslations("Bookings");
  const format = await getFormatter();
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const actions = actionsFor(booking);
  let contact: Contact | null = null;
  if (actions.contact) {
    try {
      contact = await unwrap(
        api.GET("/v1/properties/{slug}/contact", {
          params: { path: { slug: booking.property.slug } },
        }),
      );
    } catch (error) {
      if (!(error instanceof ApiError && (error.status === 403 || error.status === 404))) {
        throw error;
      }
    }
  }
  const next = t(`next.${booking.status}`, {
    time: when(
      booking.status === "token_secured" && booking.confirmBy !== null
        ? booking.confirmBy
        : booking.holdExpiresAt,
    ),
    date: dayText(booking.moveIn),
  });
  const { cancellation } = booking;
  const refund =
    cancellation === null
      ? ""
      : cancellation.refundPaise === 0
        ? t("actions.refundNothing")
        : cancellation.late
          ? t("actions.refundLate", { amount: formatINR(cancellation.refundPaise) })
          : t("actions.refundFull", { amount: formatINR(cancellation.refundPaise) });
  const money: [string, string, string | null][] = [
    [
      t("money.monthly"),
      t("money.perMonth", { amount: formatINR(booking.monthlyRentPaise) }),
      null,
    ],
    [t("money.token"), formatINR(booking.tokenPaise), t("money.tokenNote")],
    [t("money.dueAtMoveIn"), formatINR(booking.dueAtMoveInPaise), null],
    [t("money.deposit"), formatINR(booking.depositPaise), null],
    ...(booking.monthlyChargesPaise === 0
      ? []
      : [
          [
            t("money.monthlyCharges"),
            t("money.perMonth", { amount: formatINR(booking.monthlyChargesPaise) }),
            null,
          ] as [string, string, null],
        ]),
    ...(booking.oneTimeChargesPaise === 0
      ? []
      : [
          [t("money.oneTimeCharges"), formatINR(booking.oneTimeChargesPaise), null] as [
            string,
            string,
            null,
          ],
        ]),
  ];

  return (
    <div className="mx-auto w-full max-w-2xl space-y-10 px-4 py-10 sm:py-16">
      <div className="space-y-3">
        <Link
          href={BOOKINGS_PATH}
          className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
        >
          {t("back")}
        </Link>
        <p className="text-sm font-medium text-muted-foreground">
          {t("code", { code: booking.code })}
        </p>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
          <Link
            href={`/pg/${booking.property.slug}` as Route}
            className="underline-offset-4 hover:underline"
          >
            {booking.property.name}
          </Link>
        </h1>
        <p className="text-muted-foreground">
          {`${booking.roomType} · ${booking.property.locality} · ${t("stay", {
            months: booking.stayMonths,
            date: dayText(booking.plannedMoveOut),
          })}`}
        </p>
      </div>

      <section aria-labelledby="status-title" className="space-y-2 rounded-lg border p-4">
        <h2 id="status-title" className="text-lg font-semibold">
          {t(`status.${booking.status}`)}
        </h2>
        <p>{next}</p>
      </section>

      <BookingActions
        booking={booking}
        policyPath={trustPages.refunds}
        text={{
          cancel: t("actions.cancel"),
          confirmTitle: t("actions.confirmTitle", { code: booking.code }),
          refund,
          policy: t("actions.policy"),
          confirm: t("actions.confirm"),
          keep: t("actions.keep"),
          cancelling: t("actions.cancelling"),
          changed: t("actions.changed"),
          failed: t("actions.failed"),
          findAnother: t("actions.findAnother"),
        }}
      />

      {contact === null ? null : (
        <section aria-labelledby="where-title" className="space-y-2">
          <h2 id="where-title" className="text-lg font-semibold">
            {t("where.title")}
          </h2>
          <dl className="space-y-2">
            <div>
              <dt className="text-sm text-muted-foreground">{t("where.address")}</dt>
              <dd>{contact.addressLine}</dd>
            </div>
            {contact.ownerPhone === null ? null : (
              <div>
                <dt className="text-sm text-muted-foreground">{t("where.ownerPhone")}</dt>
                <dd>
                  <a href={`tel:${contact.ownerPhone}`} className="underline underline-offset-4">
                    {contact.ownerPhone}
                  </a>
                </dd>
              </div>
            )}
          </dl>
        </section>
      )}

      <section aria-labelledby="money-title" className="space-y-3">
        <h2 id="money-title" className="text-lg font-semibold">
          {t("money.title")}
        </h2>
        <dl className="divide-y rounded-lg border">
          {money.map(([label, value, note]) => (
            <div key={label} className="flex flex-wrap items-baseline justify-between gap-2 p-3">
              <dt>
                {label}
                {note === null ? null : (
                  <span className="block text-sm text-muted-foreground">{note}</span>
                )}
              </dt>
              <dd className="font-medium">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="text-sm text-muted-foreground">{t("money.toOwner")}</p>
      </section>

      <section aria-labelledby="history-title" className="space-y-3">
        <h2 id="history-title" className="text-lg font-semibold">
          {t("history")}
        </h2>
        <ol className="space-y-2">
          {booking.timeline.map((step) => (
            <li key={`${step.event}-${step.at}`} className="flex flex-wrap justify-between gap-2">
              <span>{t(`events.${step.event}` as "events.hold")}</span>
              <time dateTime={step.at} className="text-sm text-muted-foreground">
                {when(step.at)}
              </time>
            </li>
          ))}
        </ol>
      </section>

      <p className="text-sm text-muted-foreground">
        {t("help", { code: booking.code })}{" "}
        <Link
          href={trustPages.contact}
          className="font-medium text-primary underline underline-offset-4"
        >
          {t("contactUs")}
        </Link>
      </p>
    </div>
  );
}
