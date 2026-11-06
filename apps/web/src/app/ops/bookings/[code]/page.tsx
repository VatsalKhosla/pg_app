import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { BookingDesk } from "@/components/ops/booking-desk";
import { LiveRefresh } from "@/components/ops/live-refresh";
import { RefundDesk } from "@/components/ops/refund-desk";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import {
  OPS_BOOKINGS_PATH,
  OPS_DISPUTES_PATH,
  OPS_REFUNDS_PATH,
  OPS_VISITS_PATH,
} from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { dayText } from "@/lib/format/days";
import { formatINR } from "@/lib/money";

// The form's hint only; the API decides (ARCHITECTURE §17).
const SECOND_PERSON_ABOVE_PAISE = 500_000;

export async function generateMetadata({
  params,
}: PageProps<"/ops/bookings/[code]">): Promise<Metadata> {
  const { code } = await params;
  const t = await getTranslations("Ops.bookings");
  return { title: `${t("metaTitle")} ${code}` };
}

/**
 * One booking, run from one page (step 5.10, ADR 0054): what it's waiting for, whom to call, the
 * money as the API has it, what ops may do now, and everything that happened, with who did it and
 * why. Nobody needs the database for any of it.
 */
export default async function OpsBookingPage({ params }: PageProps<"/ops/bookings/[code]">) {
  const { code } = await params;
  await requireOps(`${OPS_BOOKINGS_PATH}/${code}` as Route);
  const api = await getServerApi();
  let booking;
  try {
    booking = await unwrap(api.GET("/v1/ops/bookings/{code}", { params: { path: { code } } }));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const payments = await unwrap(
    api.GET("/v1/ops/bookings/{code}/payments", { params: { path: { code } } }),
  );
  const [t, format, desk, refunds] = await Promise.all([
    getTranslations("Ops.bookings"),
    getFormatter(),
    getTranslations("Ops.refunds.desk"),
    getTranslations("Ops.refunds"),
  ]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  // Today in India: a move-out can't be later.
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const { dispute, timer } = booking;
  const stay: [string, string][] = [
    [t("detail.room"), `${booking.roomType} · ${booking.room} · ${booking.bed}`],
    [t("detail.moveIn"), dayText(booking.moveIn)],
    [t("detail.plannedMoveOut"), dayText(booking.plannedMoveOut)],
    ...(booking.movedOutOn === null
      ? []
      : ([[t("detail.movedOutOn"), dayText(booking.movedOutOn)]] as [string, string][])),
    ...(booking.status === "held"
      ? ([[t("detail.holdEnds"), when(booking.holdExpiresAt)]] as [string, string][])
      : []),
    ...(booking.status === "token_secured" && booking.confirmBy !== null
      ? ([[t("detail.confirmBy"), when(booking.confirmBy)]] as [string, string][])
      : []),
    ...(booking.checkedInAt === null
      ? []
      : ([[t("detail.movedIn"), when(booking.checkedInAt)]] as [string, string][])),
    ...(booking.checkWindowEndsAt === null
      ? []
      : ([[t("detail.windowEnds"), when(booking.checkWindowEndsAt)]] as [string, string][])),
  ];
  const money: [string, string][] = [
    [t("detail.rent"), formatINR(booking.monthlyRentPaise)],
    [t("detail.token"), formatINR(booking.tokenPaise)],
    [t("detail.dueAtMoveIn"), formatINR(booking.dueAtMoveInPaise)],
    [t("detail.deposit"), formatINR(booking.depositPaise)],
    [t("detail.monthlyCharges"), formatINR(booking.monthlyChargesPaise)],
    [t("detail.oneTimeCharges"), formatINR(booking.oneTimeChargesPaise)],
    [t("detail.fee"), formatINR(booking.feePaise)],
    [t("detail.gst"), formatINR(booking.gstPaise)],
    [t("detail.feeTotal"), formatINR(booking.ownerFeeTotalPaise)],
  ];

  return (
    <div className="space-y-8">
      <LiveRefresh />
      <div className="space-y-2">
        <Link
          href={OPS_BOOKINGS_PATH}
          className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
        >
          {t("detail.back")}
        </Link>
        <h1 className="font-display text-title-1 text-foreground">
          {t("detail.title", { code: booking.code, pg: booking.property.name })}
        </h1>
        <p className="text-muted-foreground">
          {t(`status.${booking.status}`)} · {t(`channels.${booking.channel}`)} ·{" "}
          {booking.property.locality}
        </p>
        {timer === null ? null : (
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
            {t(`timer.${timer.kind}`, { since: when(timer.since), due: when(timer.due) })}
            {timer.late ? (
              <span className="rounded-full bg-destructive-soft px-2.5 py-0.5 text-xs font-semibold text-destructive-soft-foreground">
                {t("late")}
              </span>
            ) : null}
          </p>
        )}
        {booking.cancelledAt === null ? null : (
          <p className="text-sm">
            {t("detail.ended", {
              when: when(booking.cancelledAt),
              kind: t(`events.${booking.cancellationKind ?? "cancel"}` as "events.cancel"),
            })}
          </p>
        )}
      </div>

      <section
        aria-labelledby="desk"
        className="space-y-4 rounded-2xl border border-border/80 bg-card p-6 shadow-xs"
      >
        <h2 id="desk" className="font-display text-title-3 text-foreground">
          {t("detail.do")}
        </h2>
        {dispute === null ? null : (
          <p>
            <Link
              href={`${OPS_DISPUTES_PATH}/${dispute.id}` as Route}
              className="font-medium text-primary underline underline-offset-4"
            >
              {dispute.status === "open" ? t("detail.settleDispute") : t("detail.seeDispute")}
            </Link>
          </p>
        )}
        {booking.actions.length === 0 ? (
          dispute?.status === "open" ? null : (
            <p className="text-muted-foreground">{t("detail.nothingToDo")}</p>
          )
        ) : (
          <BookingDesk code={booking.code} actions={booking.actions} today={today} />
        )}
      </section>

      <section
        aria-labelledby="people"
        className="space-y-3 rounded-2xl border border-border/80 bg-card p-6 shadow-xs"
      >
        <h2 id="people" className="font-display text-title-3 text-foreground">
          {t("detail.people")}
        </h2>
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          <div>
            <dt className="text-sm text-muted-foreground">{t("detail.student")}</dt>
            <dd>
              {booking.studentContact.name ?? t("noName")} ·{" "}
              <a
                href={`tel:${booking.studentContact.phone}`}
                className="font-medium text-primary underline underline-offset-4"
              >
                {booking.studentContact.phone}
              </a>
            </dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">{t("detail.owner")}</dt>
            <dd>
              {booking.ownerContact.name ?? t("noName")} ·{" "}
              <a
                href={`tel:${booking.ownerContact.phone}`}
                className="font-medium text-primary underline underline-offset-4"
              >
                {booking.ownerContact.phone}
              </a>
            </dd>
          </div>
        </dl>
        {booking.ownerCancellations === 0 ? null : (
          <p className="text-sm font-medium text-destructive">
            {t("detail.ownerCancellations", { count: booking.ownerCancellations })}
          </p>
        )}
        {booking.visit === null ? null : (
          <p className="text-sm">
            <Link
              href={`${OPS_VISITS_PATH}/${booking.visit}` as Route}
              className="font-medium text-primary underline underline-offset-4"
            >
              {t("detail.seeVisit")}
            </Link>
          </p>
        )}
      </section>

      <section
        aria-labelledby="stay"
        className="space-y-3 rounded-2xl border border-border/80 bg-card p-6 shadow-xs"
      >
        <h2 id="stay" className="font-display text-title-3 text-foreground">
          {t("detail.stay")}
        </h2>
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          {stay.map(([label, value]) => (
            <div key={label}>
              <dt className="text-sm text-muted-foreground">{label}</dt>
              <dd className="font-medium text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section
        aria-labelledby="money"
        className="space-y-3 rounded-2xl border border-border/80 bg-card p-6 shadow-xs"
      >
        <h2 id="money" className="font-display text-title-3 text-foreground">
          {t("detail.money")}
        </h2>
        <dl className="divide-y divide-border/60 rounded-xl border border-border/70 bg-surface/50 text-sm">
          {money.map(([label, value]) => (
            <div
              key={label}
              className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-2.5"
            >
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-medium text-foreground tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section
        aria-labelledby="payments"
        className="space-y-4 rounded-2xl border border-border/80 bg-card p-6 shadow-xs"
      >
        <h2 id="payments" className="font-display text-title-3 text-foreground">
          {desk("title")}
        </h2>
        {payments.items.length === 0 ? (
          <p className="text-muted-foreground">{desk("none")}</p>
        ) : (
          payments.items.map((payment) => (
            <div
              key={payment.id}
              className="space-y-2 rounded-xl border border-border/70 bg-surface/50 p-4"
            >
              <p className="font-semibold text-foreground tabular-nums">
                {desk("payment", {
                  amount: formatINR(payment.amountPaise),
                  status: desk(`paymentStatus.${payment.status}`),
                })}
              </p>
              {payment.capturedAt === null ? null : (
                <p className="text-sm text-muted-foreground">
                  {desk("paidOn", {
                    when: format.dateTime(new Date(payment.capturedAt), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }),
                  })}
                </p>
              )}
              {payment.providerOrderId === null ? null : (
                <p className="text-sm break-all text-muted-foreground">
                  {desk("gatewayIds", {
                    provider: payment.provider,
                    order: payment.providerOrderId,
                    payment: payment.providerPaymentId ?? "—",
                  })}
                </p>
              )}
              {payment.refunds.length === 0 ? null : (
                <ul className="space-y-2">
                  {payment.refunds.map((refund) => (
                    <li key={refund.id} className="text-sm">
                      <p className="font-medium">
                        {desk("refund", {
                          amount: formatINR(refund.amountPaise),
                          status: refunds(`status.${refund.status}`),
                        })}
                      </p>
                      <p>{desk("refundWhy", { reason: refund.reason })}</p>
                      {refund.failure === null ? null : (
                        <p className="text-destructive">{refund.failure}</p>
                      )}
                      {refund.reference === null ? null : (
                        <p>{desk("refundBank", { reference: refund.reference })}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {payment.refunds.some((refund) => refund.status === "awaiting_approval") ? (
                <Link
                  href={OPS_REFUNDS_PATH}
                  className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
                >
                  {refunds("status.awaiting_approval")}
                </Link>
              ) : null}
              {payment.refundablePaise <= 0 ? null : (
                <RefundDesk
                  paymentId={payment.id}
                  refundablePaise={payment.refundablePaise}
                  secondPersonAbovePaise={SECOND_PERSON_ABOVE_PAISE}
                  text={{
                    open: desk("open"),
                    title: desk("formTitle"),
                    amount: desk("amount"),
                    left: desk("left", { amount: formatINR(payment.refundablePaise) }),
                    reason: desk("reason"),
                    needAmount: desk("needAmount"),
                    needReason: desk("needReason"),
                    next: desk("next"),
                    confirmTitle: desk("confirmTitle", { amount: "{amount}" }),
                    confirmBody: desk("confirmBody"),
                    confirmWaits: desk("confirmWaits"),
                    yes: desk("yes"),
                    back: desk("back"),
                    close: desk("close"),
                    sent: desk("sent"),
                    waits: desk("waits"),
                    tooMuch: desk("tooMuch"),
                    failed: desk("failed"),
                  }}
                />
              )}
            </div>
          ))
        )}
      </section>

      <section
        aria-labelledby="history"
        className="space-y-4 rounded-2xl border border-border/80 bg-card p-6 shadow-xs"
      >
        <h2 id="history" className="font-display text-title-3 text-foreground">
          {t("detail.history")}
        </h2>
        <ol className="space-y-3">
          {booking.history.map((entry) => (
            <li key={`${entry.event}-${entry.at}`} className="space-y-0.5">
              <p className="flex flex-wrap justify-between gap-2">
                <span className="font-medium text-foreground">
                  {t(`events.${entry.event}` as "events.hold")}
                </span>
                <time dateTime={entry.at} className="text-sm text-muted-foreground tabular-nums">
                  {when(entry.at)}
                </time>
              </p>
              <p className="text-sm text-muted-foreground">
                {t(`status.${entry.toStatus}`)} ·{" "}
                {entry.byName === null
                  ? t(`by.${entry.by}`)
                  : t("byName", { name: entry.byName, party: t(`by.${entry.by}`) })}
              </p>
              {entry.note === null ? null : (
                <p className="text-sm whitespace-pre-line">{t("note", { note: entry.note })}</p>
              )}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
