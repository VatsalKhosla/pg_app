import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { PayToken } from "@/components/bookings/pay-token";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireSession } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Bookings.pay");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/**
 * Paying a held booking's token (step 6.1, ADR 0056). It's a page of its own because Razorpay's
 * checkout needs a wider security policy than anywhere else on the site, and a browser takes a
 * page's policy only on a full page load. So the booking page links here with a plain link, and
 * only this page's policy allows it (src/proxy.ts, next.config.ts).
 */
export default async function PayPage({ params }: PageProps<"/bookings/[code]/pay">) {
  const { code } = await params;
  const path = `${BOOKINGS_PATH}/${code}`;
  await requireSession(`${path}/pay` as Route);
  const api = await getServerApi();
  let booking: Schemas["StudentBooking"];
  try {
    booking = await unwrap(api.GET("/v1/bookings/{code}", { params: { path: { code } } }));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  if (!booking.canPay) redirect(path as Route);

  const t = await getTranslations("Bookings.pay");
  const money = await getTranslations("Bookings.money");
  const format = await getFormatter();
  const token = formatINR(booking.tokenPaise);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 px-4 py-10 sm:py-16">
      <div className="space-y-3">
        <Link
          href={path as Route}
          className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
        >
          {t("back")}
        </Link>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
          {t("title", { amount: token })}
        </h1>
        <p>{t("what", { pg: booking.property.name, code: booking.code })}</p>
        <p>
          {t("until", {
            time: format.dateTime(new Date(booking.holdExpiresAt), {
              dateStyle: "medium",
              timeStyle: "short",
            }),
          })}
        </p>
        <p className="text-muted-foreground">{money("tokenNote")}</p>
      </div>
      <PayToken
        code={booking.code}
        bookingPath={path}
        text={{
          pay: t("pay", { amount: token }),
          description: t("description", { code: booking.code }),
          opening: t("opening"),
          checking: t("checking"),
          waiting: t("waiting"),
          checkAgain: t("checkAgain"),
          notPaid: t("notPaid"),
          late: t("late", { code: booking.code }),
          unverified: t("unverified", { code: booking.code }),
          changed: t("changed"),
          failed: t("failed"),
          backToBooking: t("backToBooking"),
          test: {
            title: t("test.title"),
            body: t("test.body"),
            pay: t("test.pay", { amount: token }),
            cancel: t("test.cancel"),
          },
        }}
      />
    </div>
  );
}
