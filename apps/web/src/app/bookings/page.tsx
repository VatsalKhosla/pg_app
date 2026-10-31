import type { Metadata, Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { buttonVariants } from "@/components/ui/button";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireSession } from "@/lib/auth/session";
import { dayText } from "@/lib/format/days";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Bookings");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/** A student's bookings, newest first (step 5.5, ADR 0049); each opens its own page. */
export default async function BookingsPage() {
  await requireSession(BOOKINGS_PATH);
  const api = await getServerApi();
  const { items } = await unwrap(api.GET("/v1/bookings"));
  const t = await getTranslations("Bookings");

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
          {items.map((booking) => (
            <li key={booking.code} className="space-y-2 rounded-lg border p-4">
              <p className="text-sm font-medium text-muted-foreground">
                {t(`status.${booking.status}`)}
              </p>
              <p className="font-semibold">{booking.property.name}</p>
              <p className="text-sm text-muted-foreground">
                {`${booking.roomType} · ${t("moveIn", { date: dayText(booking.moveIn) })}`}
              </p>
              <Link
                href={`${BOOKINGS_PATH}/${booking.code}` as Route}
                className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
              >
                {t("open", { code: booking.code })}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
