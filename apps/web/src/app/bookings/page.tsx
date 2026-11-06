import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireSession } from "@/lib/auth/session";
import { dayText } from "@/lib/format/days";

type Status = Schemas["StudentBooking"]["status"];

function statusVariant(status: Status): "brand" | "success" | "warning" | "neutral" {
  switch (status) {
    case "held":
    case "token_secured":
      return "brand";
    case "confirmed":
    case "checked_in":
    case "active":
    case "completed":
      return "success";
    case "disputed":
      return "warning";
    case "expired":
    case "cancelled":
    case "rejected":
    case "no_show":
    case "refunded":
      return "neutral";
  }
}

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
    <div className="mx-auto w-full max-w-3xl space-y-8 px-gutter py-10 sm:py-16">
      <div className="space-y-3">
        <h1 className="text-title-1 text-foreground">{t("title")}</h1>
        <p className="max-w-prose text-muted-foreground">{t("intro")}</p>
      </div>
      {items.length === 0 ? (
        <Card variant="flat" className="space-y-4 rounded-2xl border-dashed p-8">
          <p className="text-muted-foreground">{t("none")}</p>
          <Link href="/search" className={buttonVariants({ size: "lg", shape: "pill" })}>
            {t("find")}
          </Link>
        </Card>
      ) : (
        <ul className="space-y-4">
          {items.map((booking) => (
            <li
              key={booking.code}
              className="flex flex-col justify-between gap-4 rounded-2xl border bg-card p-5 text-card-foreground shadow-xs sm:flex-row sm:items-center sm:p-6"
            >
              <div className="space-y-2">
                <div>
                  <Badge variant={statusVariant(booking.status)}>
                    {t(`status.${booking.status}`)}
                  </Badge>
                </div>
                <p className="font-display text-lg font-semibold text-foreground">
                  {booking.property.name}
                </p>
                <p className="text-sm text-muted-foreground">
                  {`${booking.roomType} · ${t("moveIn", { date: dayText(booking.moveIn) })}`}
                </p>
              </div>
              <Link
                href={`${BOOKINGS_PATH}/${booking.code}` as Route}
                className={buttonVariants({ variant: "soft", size: "sm", shape: "pill" })}
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
