import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { NotSetUp } from "@/components/owner/not-set-up";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OWNER_BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";
import { getOwnProfile } from "@/lib/owner/server";
import { cn } from "@/lib/utils";

const FILTERS = ["token_secured", "confirmed", "checked_in", "active"] as const;
type Filter = (typeof FILTERS)[number];
const PAGE = 50;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner.bookings");
  return { title: t("metaTitle") };
}

/**
 * The owner's bookings inbox (step 7.3): newest first, those waiting for an answer with their
 * deadline, and the visits booked to their PGs in the next two weeks.
 */
export default async function OwnerBookingsPage({ searchParams }: PageProps<"/owner/bookings">) {
  await requireOwner(OWNER_BOOKINGS_PATH);
  const owner = await getOwnProfile();
  if (owner === null) return <NotSetUp />;
  const asked = (await searchParams).status;
  const status: Filter | undefined = FILTERS.find((each) => each === asked);
  const api = await getServerApi();
  const [bookings, visits] = await Promise.all([
    unwrap(api.GET("/v1/owner/bookings", { params: { query: { status, limit: PAGE } } })),
    unwrap(api.GET("/v1/owner/visits", { params: { query: { days: 14 } } })),
  ]);
  const [t, format] = await Promise.all([getTranslations("Owner.bookings"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const day = (date: string) =>
    format.dateTime(new Date(`${date}T00:00:00+05:30`), { dateStyle: "medium" });
  const filters: { href: Route; label: string; current: boolean }[] = [
    { href: OWNER_BOOKINGS_PATH, label: t("all"), current: status === undefined },
    ...FILTERS.map((each) => ({
      href: `${OWNER_BOOKINGS_PATH}?status=${each}` as Route,
      label: t(`status.${each}`),
      current: each === status,
    })),
  ];

  return (
    <>
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <nav aria-label={t("filter")} className="flex flex-wrap gap-2">
        {filters.map((filter) => (
          <Link
            key={filter.href}
            href={filter.href}
            aria-current={filter.current ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-md border px-3 text-sm",
              filter.current && "border-primary bg-accent font-medium",
            )}
          >
            {filter.label}
          </Link>
        ))}
      </nav>
      {bookings.items.length === 0 ? (
        <p className="text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="space-y-3">
          {bookings.items.map((booking) => (
            <li key={booking.code} className="space-y-1 rounded-lg border p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <Link
                  href={`${OWNER_BOOKINGS_PATH}/${booking.code}` as Route}
                  aria-label={t("open", { code: booking.code })}
                  className="font-medium text-primary underline underline-offset-4"
                >
                  {t("line", {
                    code: booking.code,
                    place: booking.property.name,
                    roomType: booking.roomType,
                  })}
                </Link>
                <span className="text-sm font-medium">{t(`status.${booking.status}`)}</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {t("moveIn", {
                  date: day(booking.moveIn),
                  months: booking.stayMonths,
                  rent: formatINR(booking.monthlyRentPaise),
                })}
              </p>
              {booking.status === "token_secured" && booking.confirmBy !== null ? (
                <p className="text-sm font-medium">
                  {t("answerBy", { when: when(booking.confirmBy) })}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <section aria-labelledby="visits-title" className="space-y-3">
        <h2 id="visits-title" className="text-lg font-semibold">
          {t("visitsTitle")}
        </h2>
        {visits.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("visitsNone")}</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {visits.items.map((visit) => (
              <li key={visit.id} className="p-3 text-sm">
                {visit.student === null
                  ? t("visitNoName", { when: when(visit.scheduledAt), place: visit.place })
                  : t("visit", {
                      when: when(visit.scheduledAt),
                      place: visit.place,
                      student: visit.student,
                    })}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
