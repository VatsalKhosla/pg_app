import type { Schemas } from "@pg-platform/api-client";
import { ArrowLeft } from "lucide-react";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { getFormatter, getMessages, getTranslations } from "next-intl/server";

import { BookingActions } from "@/components/bookings/booking-actions";
import { CheckWindow } from "@/components/bookings/check-window";
import { DisputeForm } from "@/components/bookings/dispute-form";
import { TokenTrack } from "@/components/bookings/token-track";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSearchPage } from "@/lib/api/public";
import { getServerApi } from "@/lib/api/server";
import { BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireSession } from "@/lib/auth/session";
import { actionsFor } from "@/lib/bookings/actions";
import { dayText } from "@/lib/format/days";
import { formatINR } from "@/lib/money";
import { serializeSearch } from "@/lib/search/params";
import { trustPages } from "@/lib/trust/pages";
import { cn } from "@/lib/utils";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Bookings");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

type Contact = Schemas["ListingContact"];
type Rebook = NonNullable<Schemas["StudentBooking"]["rebook"]>;

// PGs like this one to show on the page; the search link has the rest.
const SIMILAR = 3;

/**
 * PGs like the booking's, with a bed free for the month the student needs: the API's search for
 * them, less this PG. Help to book again, never a reason the page can't show.
 */
async function similarTo(rebook: Rebook, slug: string) {
  const query = {
    locality: rebook.locality,
    occupancy: rebook.occupancy,
    gender: rebook.gender,
    move_in_month: rebook.moveInMonth,
    budget_max_paise: rebook.budgetMaxPaise,
    available: true,
  };
  try {
    const found = await getSearchPage({ ...query, limit: SIMILAR + 1 });
    const cards = "page" in found ? found.page.items : [];
    return {
      cards: cards.filter((card) => card.slug !== slug).slice(0, SIMILAR),
      more: serializeSearch("/search", query) as Route,
    };
  } catch {
    return { cards: [], more: serializeSearch("/search", query) as Route };
  }
}

/**
 * A student's booking (steps 5.5 to 5.7, ADRs 0049 to 0051): what happens next, what they pay and
 * to whom, where to go once the owner confirms (the address and the owner's phone show only then;
 * CLAUDE.md rule 11), what happened so far, cancelling, with what it gives back shown first,
 * saying they've moved in, after which their time to check the room counts down, reporting a
 * room that isn't as shown, and PGs like it once a booking ended through no fault of theirs.
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
  const paid = await unwrap(
    api.GET("/v1/bookings/{code}/payments", { params: { path: { code } } }),
  );
  const t = await getTranslations("Bookings");
  const messages = await getMessages();
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
  // The one deadline each status has: the hold's, the owner's, or the end of the student's time
  // to check the room.
  const deadline =
    (booking.status === "token_secured"
      ? booking.confirmBy
      : booking.status === "checked_in"
        ? booking.checkWindowEndsAt
        : null) ?? booking.holdExpiresAt;
  const next = t(`next.${booking.status}`, {
    time: when(deadline),
    date: dayText(booking.moveIn),
    opens: booking.checkInOpensOn === null ? "" : dayText(booking.checkInOpensOn),
  });
  const similar =
    booking.rebook === null ? null : await similarTo(booking.rebook, booking.property.slug);
  const { cancellation, dispute } = booking;
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
    <div className="mx-auto w-full max-w-3xl space-y-8 px-gutter py-10 sm:py-16">
      <div className="space-y-3">
        <Link
          href={BOOKINGS_PATH}
          className="inline-flex min-h-8 items-center gap-1.5 text-sm font-semibold text-primary underline underline-offset-4"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          {t("back")}
        </Link>
        <p className="relative inline-block rounded-full border border-dusk-border bg-dusk-soft px-3 py-1 font-mono text-xs font-semibold tracking-wider text-dusk-soft-foreground uppercase">
          {t("code", { code: booking.code })}
        </p>
        <h1 className="text-title-1 font-medium text-foreground">
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

      <Card
        asChild
        variant="ink"
        className="relative space-y-3 overflow-hidden rounded-3xl p-6 shadow-sm"
      >
        <section aria-labelledby="status-title">
          <h2 id="status-title" className="text-title-3 font-semibold text-foreground">
            {t(`status.${booking.status}`)}
          </h2>
          <p className="text-sm leading-relaxed text-foreground sm:text-base">{next}</p>
          {dispute === null ? null : (
            <p className="rounded-xl bg-marigold-soft px-4 py-3 text-sm font-medium text-marigold-soft-foreground">
              {t("disputeStatus", {
                date: dayText(dispute.openedAt.slice(0, 10)),
                reason: t(`dispute.reasons.${dispute.reason}`),
                status: t(`dispute.status.${dispute.status}`),
              })}
            </p>
          )}
          {booking.status === "checked_in" && booking.checkWindowEndsAt !== null ? (
            <NextIntlClientProvider messages={{ Bookings: { window: messages.Bookings.window } }}>
              <CheckWindow endsAt={booking.checkWindowEndsAt} />
            </NextIntlClientProvider>
          ) : null}
        </section>
      </Card>

      <TokenTrack status={booking.status} token={formatINR(booking.tokenPaise)} />

      {booking.canPay ? (
        // A plain link, not next/link: checkout needs the payment page's own security policy, and
        // a browser takes a page's policy only on a full page load (ADR 0056).
        <a
          href={`${BOOKINGS_PATH}/${booking.code}/pay`}
          className={cn(buttonVariants({ size: "lg", shape: "pill" }), "w-full sm:w-auto")}
        >
          {t("pay.link", { amount: formatINR(booking.tokenPaise) })}
        </a>
      ) : null}

      {actions.dispute ? (
        <NextIntlClientProvider messages={{ Bookings: { dispute: messages.Bookings.dispute } }}>
          <DisputeForm code={booking.code} />
        </NextIntlClientProvider>
      ) : null}

      {similar === null ? null : (
        <Card asChild className="space-y-4 rounded-2xl p-6">
          <section aria-labelledby="similar-title">
            <h2 id="similar-title" className="text-title-3 text-foreground">
              {t("similar.title")}
            </h2>
            {similar.cards.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("similar.none")}</p>
            ) : (
              <ul className="divide-y rounded-xl border bg-surface/60">
                {similar.cards.map((card) => (
                  <li
                    key={card.id}
                    className="flex flex-wrap items-baseline justify-between gap-2 p-3.5"
                  >
                    <Link
                      href={`/pg/${card.slug}` as Route}
                      className="font-medium text-foreground underline-offset-4 hover:underline"
                    >
                      {card.name}
                    </Link>
                    <span className="text-sm text-muted-foreground tabular-nums">
                      {t("similar.card", {
                        locality: card.locality.name,
                        rent: formatINR(card.minRentPaise),
                      })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <Link
              href={similar.more}
              className="inline-flex min-h-8 items-center text-sm font-medium text-primary underline underline-offset-4"
            >
              {t("similar.more")}
            </Link>
          </section>
        </Card>
      )}

      <BookingActions
        booking={booking}
        policyPath={trustPages.refunds}
        text={{
          checkIn: {
            start: t("checkIn.start"),
            title: t("checkIn.title", { pg: booking.property.name }),
            body: t("checkIn.body", { hours: booking.checkWindowHours }),
            confirm: t("checkIn.confirm"),
            notYet: t("checkIn.notYet"),
            saving: t("checkIn.saving"),
            changed: t("checkIn.changed"),
          },
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
        <Card asChild variant="warm" className="relative space-y-4 overflow-hidden rounded-3xl p-6">
          <section aria-labelledby="where-title">
            <h2 id="where-title" className="text-title-3 font-semibold text-foreground">
              {t("where.title")}
            </h2>
            <dl className="grid gap-4 rounded-2xl border border-neem-border bg-card p-4 sm:grid-cols-2">
              <div className="space-y-1">
                <dt className="text-sm text-muted-foreground">{t("where.address")}</dt>
                <dd className="text-sm font-medium text-foreground">{contact.addressLine}</dd>
              </div>
              {contact.ownerPhone === null ? null : (
                <div className="space-y-1">
                  <dt className="text-sm text-muted-foreground">{t("where.ownerPhone")}</dt>
                  <dd className="text-sm font-medium">
                    <a
                      href={`tel:${contact.ownerPhone}`}
                      className="text-primary underline underline-offset-4"
                    >
                      {contact.ownerPhone}
                    </a>
                  </dd>
                </div>
              )}
            </dl>
          </section>
        </Card>
      )}

      {paid.items.some(
        (payment) =>
          payment.capturedAt !== null ||
          payment.status === "blocked" ||
          payment.status === "released",
      ) ? (
        <Card asChild variant="warm" className="relative space-y-4 overflow-hidden rounded-3xl p-6">
          <section aria-labelledby="paid-title">
            <h2 id="paid-title" className="text-title-3 font-semibold text-foreground">
              {t("paid.title")}
            </h2>
            <ul className="space-y-3">
              {paid.items.map((payment, index) =>
                payment.status === "blocked" || payment.status === "released" ? (
                  // A token blocked by a UPI one-time mandate (step 6.7): not taken, or given back.
                  <li
                    key={`${payment.status}-${String(index)}`}
                    className="rounded-xl border border-marigold-border bg-card p-4 text-sm text-foreground tabular-nums"
                  >
                    <p>{t(`paid.${payment.status}`, { amount: formatINR(payment.amountPaise) })}</p>
                  </li>
                ) : payment.capturedAt === null ? null : (
                  <li
                    key={payment.capturedAt}
                    className="space-y-2 rounded-xl border border-marigold-border bg-card p-4 text-sm text-foreground tabular-nums"
                  >
                    <p className="font-medium">
                      {t("paid.token", {
                        amount: formatINR(payment.amountPaise),
                        date: when(payment.capturedAt),
                      })}
                    </p>
                    {payment.refunds.map((refundItem) => (
                      <div
                        key={refundItem.requestedAt + String(refundItem.amountPaise)}
                        className="space-y-0.5 text-muted-foreground"
                      >
                        <p className="text-foreground">
                          {t(`paid.refund.${refundItem.status as "requested"}`, {
                            amount: formatINR(refundItem.amountPaise),
                            date: when(refundItem.processedAt ?? refundItem.requestedAt),
                          })}
                        </p>
                        {refundItem.reference === null ? null : (
                          <p className="text-xs text-muted-foreground">
                            {t("paid.reference", { reference: refundItem.reference })}
                          </p>
                        )}
                      </div>
                    ))}
                  </li>
                ),
              )}
            </ul>
          </section>
        </Card>
      ) : null}

      <Card asChild variant="warm" className="relative space-y-4 overflow-hidden rounded-3xl p-6">
        <section aria-labelledby="money-title">
          <h2 id="money-title" className="text-title-3 font-semibold text-foreground">
            {t("money.title")}
          </h2>
          <dl className="divide-y rounded-2xl border border-marigold-border/70 bg-card">
            {money.map(([label, value, note]) => (
              <div
                key={label}
                className="flex flex-wrap items-baseline justify-between gap-2 p-3.5 text-sm"
              >
                <dt className="text-foreground">
                  {label}
                  {note === null ? null : (
                    <span className="mt-0.5 block text-xs text-muted-foreground">{note}</span>
                  )}
                </dt>
                <dd className="font-semibold text-foreground tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="text-sm text-muted-foreground">{t("money.toOwner")}</p>
        </section>
      </Card>

      <Card asChild variant="warm" className="relative space-y-4 overflow-hidden rounded-3xl p-6">
        <section aria-labelledby="history-title">
          <h2 id="history-title" className="text-title-3 font-semibold text-foreground">
            {t("history")}
          </h2>
          <ol className="divide-y rounded-2xl border border-dusk-border bg-card p-4 text-sm">
            {booking.timeline.map((step) => (
              <li
                key={`${step.event}-${step.at}`}
                className="flex flex-wrap items-baseline justify-between gap-2 py-2.5 first:pt-0 last:pb-0"
              >
                <span className="text-foreground">
                  {t(`events.${step.event}` as "events.hold")}
                </span>
                <time dateTime={step.at} className="text-xs text-muted-foreground tabular-nums">
                  {when(step.at)}
                </time>
              </li>
            ))}
          </ol>
        </section>
      </Card>

      <p className="rounded-2xl bg-surface-warm px-5 py-4 text-sm text-muted-foreground">
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
