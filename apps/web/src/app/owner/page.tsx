import {
  BookOpenCheck,
  Building2,
  CalendarClock,
  CalendarDays,
  HandCoins,
  IndianRupee,
  type LucideIcon,
  ReceiptText,
  UsersRound,
  Wallet,
} from "lucide-react";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { PeriodBars } from "@/components/charts/period-bars";
import { RingMeter } from "@/components/charts/ring-meter";
import { NotSetUp } from "@/components/owner/not-set-up";
import { BedsByPg, NeedsYouCard, StatTile } from "@/components/owner/overview";
import { brand } from "@/config/brand";
import {
  OWNER_AGREEMENT_PATH,
  OWNER_BOOKINGS_PATH,
  OWNER_HOME_PATH,
  OWNER_INVOICES_PATH,
  OWNER_PGS_PATH,
} from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";
import { getOwnerOverview, getOwnProfile, type OwnerOverview } from "@/lib/owner/server";
import { shortRupees } from "@/lib/search/labels";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner.home");
  return { title: t("metaTitle") };
}

const INDIA = "Asia/Kolkata";

/** A day the API gives (YYYY-MM-DD, India) as a moment at its start in India. */
function indianDay(day: string): Date {
  return new Date(`${day}T00:00:00+05:30`);
}

const sectionClass =
  "space-y-5 rounded-[2rem] border border-border/70 bg-card p-5 shadow-md sm:p-7";

/**
 * The owner's home (ADR 0071): first, what waits for them; then how full their PGs are and what
 * the tenants we placed have brought them, month by month; then the way to everything else.
 * Every number is the API's: nothing is worked out here but percentages for the bars.
 */
export default async function OwnerHomePage() {
  await requireOwner(OWNER_HOME_PATH);
  const owner = await getOwnProfile();
  if (owner === null) return <NotSetUp />;
  // None accepted yet, or a new version since: the agreement comes first.
  if (!owner.agreementCurrent) redirect(OWNER_AGREEMENT_PATH);
  const [t, overview] = await Promise.all([getTranslations("Owner.home"), getOwnerOverview()]);
  const format = await getFormatter();
  const details = [
    { term: t("businessName"), value: owner.businessName },
    { term: t("legalName"), value: owner.legalName },
    { term: t("gstin"), value: owner.gstin ?? t("noGstin") },
    ...(owner.email == null ? [] : [{ term: t("email"), value: owner.email }]),
    ...(owner.phone === null ? [] : [{ term: t("phone"), value: owner.phone }]),
  ];
  const links: { href: Route; title: string; note: string; Icon: LucideIcon }[] = [
    {
      href: OWNER_BOOKINGS_PATH,
      title: t("bookingsLink"),
      note: t("linksNote.bookings"),
      Icon: CalendarDays,
    },
    { href: OWNER_PGS_PATH, title: t("pgsLink"), note: t("linksNote.pgs"), Icon: Building2 },
    {
      href: OWNER_INVOICES_PATH,
      title: t("invoicesLink"),
      note: t("linksNote.invoices"),
      Icon: ReceiptText,
    },
  ];

  return (
    <>
      <header className="space-y-2">
        <h1 className="text-title-1 font-semibold tracking-tight text-foreground">
          {owner.businessName}
        </h1>
        <p className="text-body text-muted-foreground">
          {overview === null
            ? t("intro")
            : overview.beds === 0
              ? t("summaryNoBeds", {
                  date: format.dateTime(indianDay(overview.today), {
                    dateStyle: "long",
                    timeZone: INDIA,
                  }),
                })
              : t("summary", {
                  date: format.dateTime(indianDay(overview.today), {
                    dateStyle: "long",
                    timeZone: INDIA,
                  }),
                  taken: overview.bedsTaken,
                  beds: overview.beds,
                  pgs: overview.properties.length,
                })}
        </p>
      </header>

      {overview === null ? (
        <p
          role="status"
          className="rounded-2xl border border-dashed border-border bg-surface/60 p-5 text-muted-foreground"
        >
          {t("unavailable")}
        </p>
      ) : (
        <Overview overview={overview} />
      )}

      <nav aria-label={t("runTitle")} className="grid gap-4 sm:grid-cols-3">
        {links.map(({ href, title, note, Icon }) => (
          <Link
            key={href}
            href={href}
            className="group flex h-full flex-col gap-3 rounded-[1.5rem] border border-border/70 bg-card p-5 shadow-sm outline-none transition-[box-shadow,transform] duration-(--duration-base) ease-standard hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none motion-reduce:hover:translate-y-0"
          >
            <span
              aria-hidden="true"
              className="grid size-10 place-items-center rounded-xl bg-linear-to-br from-primary to-[color-mix(in_oklch,var(--sun)_70%,var(--ember))] text-white shadow-sm"
            >
              <Icon className="size-5" />
            </span>
            <span className="font-semibold text-foreground">{title}</span>
            <span className="text-sm text-muted-foreground">{note}</span>
          </Link>
        ))}
      </nav>

      <section aria-labelledby="business-title" className={sectionClass}>
        <h2 id="business-title" className="text-title-3 font-semibold tracking-tight">
          {t("detailsTitle")}
        </h2>
        <dl className="divide-y divide-border/80 rounded-xl border border-border/80 bg-surface/50">
          {details.map((detail) => (
            <div key={detail.term} className="grid gap-1 px-4 py-3 sm:grid-cols-3">
              <dt className="text-sm font-medium text-muted-foreground">{detail.term}</dt>
              <dd className="font-medium break-words text-foreground sm:col-span-2">
                {detail.value}
              </dd>
            </div>
          ))}
        </dl>
        <p className="text-sm text-muted-foreground">{t("changes")}</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border/70 pt-4">
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <BookOpenCheck aria-hidden="true" className="size-4 text-neem" />
            {t("accepted", { version: owner.agreementVersion ?? "" })}
          </p>
          <Link
            href={OWNER_AGREEMENT_PATH}
            className="inline-flex min-h-6 items-center text-sm font-semibold text-primary underline underline-offset-4 hover:text-primary-hover"
          >
            {t("read")}
          </Link>
        </div>
      </section>
    </>
  );
}

/** What waits for the owner, their beds, and what the tenants we placed have brought them. */
async function Overview({ overview }: { overview: OwnerOverview }) {
  const [t, tPgs, format] = await Promise.all([
    getTranslations("Owner.home"),
    getTranslations("Owner.pgs"),
    getFormatter(),
  ]);
  const count = (value: number) => format.number(value);
  const months = overview.months.map((month) =>
    format.dateTime(indianDay(month), { month: "short", year: "2-digit", timeZone: INDIA }),
  );
  const share = overview.beds > 0 ? Math.round((overview.bedsTaken / overview.beds) * 100) : 0;
  const needs: {
    key: string;
    href: Route;
    title: string;
    detail: string | undefined;
    Icon: LucideIcon;
    urgent: boolean;
  }[] = [
    ...(overview.bookingsToConfirm > 0
      ? [
          {
            key: "confirm",
            href: OWNER_BOOKINGS_PATH as Route,
            title: t("needs.confirm", { count: overview.bookingsToConfirm }),
            detail:
              overview.confirmBy === null
                ? undefined
                : t("needs.confirmBy", {
                    when: format.dateTime(new Date(overview.confirmBy), {
                      weekday: "short",
                      day: "numeric",
                      month: "short",
                      hour: "numeric",
                      minute: "2-digit",
                      timeZone: INDIA,
                    }),
                  }),
            Icon: HandCoins,
            urgent: true,
          },
        ]
      : []),
    ...(overview.visitsThisWeek > 0
      ? [
          {
            key: "visits",
            href: OWNER_BOOKINGS_PATH as Route,
            title: t("needs.visits", { count: overview.visitsThisWeek }),
            detail: t("needs.visitsDetail"),
            Icon: CalendarClock,
            urgent: false,
          },
        ]
      : []),
    ...(overview.invoicesUnpaid > 0
      ? [
          {
            key: "invoices",
            href: OWNER_INVOICES_PATH as Route,
            title: t("needs.invoices", { count: overview.invoicesUnpaid }),
            detail: t("needs.invoicesDetail", { amount: formatINR(overview.feesDuePaise) }),
            Icon: ReceiptText,
            urgent: false,
          },
        ]
      : []),
  ];
  const lastRent = overview.rentPaise.at(-1) ?? 0;
  const moveIns = overview.moveIns.reduce((sum, value) => sum + value, 0);

  return (
    <>
      <section aria-labelledby="needs-title" className="space-y-3">
        <h2 id="needs-title" className="text-title-3 font-semibold tracking-tight">
          {t("needs.title")}
        </h2>
        {needs.length === 0 ? (
          <p className="rounded-2xl border border-neem-border bg-neem-soft px-5 py-4 text-neem-soft-foreground">
            {t("needs.clear")}
          </p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {needs.map(({ key, ...card }) => (
              <li key={key}>
                <NeedsYouCard {...card} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="beds-title" className={sectionClass}>
        <div className="space-y-1">
          <h2 id="beds-title" className="text-title-3 font-semibold tracking-tight">
            {t("beds.title")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("beds.lead")}</p>
        </div>
        {overview.beds === 0 ? (
          <p className="text-muted-foreground">{t("beds.none")}</p>
        ) : (
          <div className="grid items-center gap-8 md:grid-cols-[minmax(0,16rem)_1fr]">
            <div className="space-y-4">
              <RingMeter value={overview.bedsTaken} total={overview.beds}>
                <p className="text-display leading-none font-semibold tabular-nums">
                  {t("beds.share", { share })}
                </p>
                <p className="mt-1 text-sm font-medium text-muted-foreground">{t("beds.taken")}</p>
              </RingMeter>
              <p className="text-center font-semibold tabular-nums">
                {t("beds.ofBeds", { taken: overview.bedsTaken, beds: overview.beds })}
              </p>
              <ul className="flex justify-center gap-5 text-sm text-muted-foreground">
                <li className="flex items-center gap-2">
                  <span aria-hidden="true" className="share-bar-fill size-3 rounded-full" />
                  {t("beds.legendTaken", { count: overview.bedsTaken })}
                </li>
                <li className="flex items-center gap-2">
                  <span aria-hidden="true" className="share-bar-track size-3 rounded-full" />
                  {t("beds.legendFree", { count: overview.beds - overview.bedsTaken })}
                </li>
              </ul>
            </div>
            <BedsByPg
              label={t("beds.list")}
              pgs={overview.properties.map((pg) => ({
                id: pg.id,
                href: `${OWNER_PGS_PATH}/${pg.id}` as Route,
                name: pg.name,
                place: t("beds.place", {
                  locality: pg.locality,
                  status: tPgs(`status.${pg.status}`),
                }),
                beds: pg.beds,
                taken: pg.bedsTaken,
                words: t("beds.pgWords", { taken: pg.bedsTaken, beds: pg.beds }),
              }))}
            />
          </div>
        )}
      </section>

      <section aria-labelledby="money-title" className={sectionClass}>
        <div className="space-y-1">
          <h2 id="money-title" className="text-title-3 font-semibold tracking-tight">
            {t("money.title")}
          </h2>
          <p className="max-w-prose text-sm text-muted-foreground">
            {t("money.lead", { brand: brand.name })}
          </p>
        </div>
        {overview.tenantsPlaced === 0 && overview.feesPaise === 0 ? (
          <p className="rounded-2xl border border-dashed border-border bg-surface/60 p-5 text-muted-foreground">
            {t("money.none", { brand: brand.name })}
          </p>
        ) : (
          <>
            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <li>
                <StatTile
                  label={t("money.placed")}
                  value={count(overview.tenantsPlaced)}
                  note={t("money.placedNote", { count: overview.tenantsNow })}
                  Icon={UsersRound}
                  tone="primary"
                />
              </li>
              <li>
                <StatTile
                  label={t("money.rentNow")}
                  value={formatINR(overview.rentNowPaise)}
                  note={t("money.rentNowNote")}
                  Icon={IndianRupee}
                  tone="neem"
                />
              </li>
              <li>
                <StatTile
                  label={t("money.booked")}
                  value={formatINR(overview.rentBookedPaise)}
                  note={t("money.bookedNote", {
                    amount: formatINR(overview.rentAfterFeesPaise),
                  })}
                  Icon={Wallet}
                  tone="dusk"
                />
              </li>
              <li>
                <StatTile
                  label={t("money.fees")}
                  value={formatINR(overview.feesPaise)}
                  note={
                    overview.feesDuePaise > 0
                      ? t("money.feesDue", { amount: formatINR(overview.feesDuePaise) })
                      : t("money.feesPaid")
                  }
                  Icon={ReceiptText}
                  tone="marigold"
                />
              </li>
            </ul>
            <div className="grid gap-5 xl:grid-cols-2">
              <PeriodBars
                id="owner-rent"
                level={3}
                title={t("money.rentChart")}
                total={t("money.rentTotal", { amount: formatINR(lastRent) })}
                periods={months}
                values={overview.rentPaise}
                axis={shortRupees}
                value={formatINR}
                tableLabel={t("money.table")}
                periodLabel={t("money.month")}
              />
              <PeriodBars
                id="owner-move-ins"
                level={3}
                title={t("money.moveInsChart")}
                total={t("money.moveInsTotal", { count: moveIns })}
                periods={months}
                values={overview.moveIns}
                axis={count}
                value={count}
                tableLabel={t("money.table")}
                periodLabel={t("money.month")}
              />
            </div>
          </>
        )}
      </section>
    </>
  );
}
