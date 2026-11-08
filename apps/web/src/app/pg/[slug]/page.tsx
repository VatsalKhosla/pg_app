import type { Schemas } from "@pg-platform/api-client";
import { Check, MapPin, ShieldCheck, Sparkles, X } from "lucide-react";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { ArchWatermark, ListingPlaceholderArt } from "@/components/brand/editorial-art";
import { LocationMap } from "@/components/map/location-map";
import { Photo } from "@/components/pg/photo";
import { QuoteCheckerNear } from "@/components/pg/quote-checker-near";
import { ViewCounter } from "@/components/pg/view-counter";
import { JsonLd } from "@/components/seo/json-ld";
import { TrackView } from "@/components/system/track-view";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { publicEnv } from "@/config/env";
import {
  getPriceCalendar,
  getPublicListing,
  type PriceCalendar,
  type PublicListing,
} from "@/lib/api/public";
import { formatDistance } from "@/lib/format/distance";
import { formatINR } from "@/lib/money";
import { DEFAULT_STAY, priceStretches, scarceBeds } from "@/lib/pricing/calendar";
import { breadcrumbJsonLd, listingJsonLd } from "@/lib/seo/json-ld";
import { cn } from "@/lib/utils";

type Category = Schemas["PublicCategory"];
type Charge = Category["mandatoryCharges"][number];

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/u;
// How far the display point is from the building at most (ADR 0021).
const APPROXIMATE_RADIUS_M = 150;

async function listingFor(slug: string): Promise<PublicListing> {
  if (!SLUG.test(slug) || slug.length > 80) notFound();
  const listing = await getPublicListing(slug);
  if (listing === null) notFound();
  return listing;
}

function lowestRent(listing: PublicListing): number | null {
  const rents = listing.categories.map((category) => category.baseRentPaise);
  return rents.length === 0 ? null : Math.min(...rents);
}

export async function generateMetadata({ params }: PageProps<"/pg/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const listing = await listingFor(slug);
  const t = await getTranslations("Pg");
  const from = lowestRent(listing);
  const title = `${listing.name}, ${listing.locality.name}`;
  const description =
    from === null
      ? listing.description.slice(0, 155)
      : t("metaDescription", {
          gender: t(`gender.${listing.genderPolicy}`),
          locality: listing.locality.name,
          from: formatINR(from),
        });
  return {
    title,
    description,
    alternates: { canonical: `/pg/${slug}` },
    openGraph: { title, description, type: "website" },
  };
}

/**
 * A PG's page (ARCHITECTURE §10.6; step 3.4, ADR 0030): photos, rooms with their rent, deposit and
 * every charge shown upfront, safety, amenities, rules and where it is, at its display point.
 * Rendered per request for the CSP nonce, from data the server caches for a minute.
 */
// What reserving on the spot can answer, each with its own words (step 5.9).
const RESERVE_ERRORS = [
  "generic",
  "VISIT_NOT_ON_SITE",
  "HOLD_LIMIT_REACHED",
  "BED_UNAVAILABLE",
  "QUOTE_EXPIRED",
  "QUOTE_USED",
  "UNAUTHENTICATED",
  "BOOKING_NEEDS_VISIT",
] as const;

// A visit id in the link: the student came from their visit to reserve on the spot (step 5.9).
const VISIT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u;

export default async function PgPage({ params, searchParams }: PageProps<"/pg/[slug]">) {
  const { slug } = await params;
  const asked = (await searchParams).visit;
  const onSpotVisit = typeof asked === "string" && VISIT.test(asked) ? asked : null;
  const listing = await listingFor(slug);
  // Without the calendar (the API briefly away), the listed rents show, with no price claims.
  const calendar = await getPriceCalendar(slug).catch(() => null);
  const rentOf = currentRent(calendar);
  const t = await getTranslations("Pg");
  const tLanding = await getTranslations("Landing");
  const visit = `/pg/${slug}/visit` as Route;
  const absolute = (path: string) => new URL(path, publicEnv.siteUrl).toString();
  const localityPath = `/pg-in/${listing.locality.slug}`;

  return (
    <div className="mx-auto w-full max-w-page space-y-10 px-gutter py-8 sm:space-y-12 sm:py-12">
      <TrackView event="pg_viewed" properties={{ slug }} />
      {/* Its owner's count of views (step 7.6): once a session, from the browser. */}
      <ViewCounter slug={slug} />
      {/* For search engines: the PG with its offers, and where it sits in the site (ADR 0032). */}
      <JsonLd
        data={[
          listingJsonLd(listing, absolute(`/pg/${slug}`), rentOf),
          breadcrumbJsonLd([
            { name: tLanding("home"), url: absolute("/") },
            {
              name: tLanding("in.title", { locality: listing.locality.name }),
              url: absolute(localityPath),
            },
            { name: listing.name, url: absolute(`/pg/${slug}`) },
          ]),
        ]}
      />
      <header className="relative flex flex-col gap-5 overflow-hidden rounded-3xl border border-marigold-border bg-surface-warm p-6 shadow-xs sm:flex-row sm:items-end sm:justify-between sm:p-8">
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-1.5"
          style={{
            backgroundImage:
              "linear-gradient(90deg, var(--primary) 0%, var(--neem) 35%, var(--marigold) 70%, var(--ember) 100%)",
          }}
        />
        <ArchWatermark tone="ember" className="absolute -right-6 -bottom-6 size-44 opacity-15" />
        <div className="relative space-y-3">
          <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-muted-foreground">
            <MapPin aria-hidden="true" className="size-4 text-ember" />
            <Link
              href={localityPath as Route}
              className="inline-flex min-h-6 items-center rounded font-semibold text-foreground underline decoration-ember/60 underline-offset-4 outline-none hover:text-primary focus-visible:ring-2 focus-visible:ring-ring"
            >
              {listing.locality.name}
            </Link>
            <span>{`· ${t(`genderShort.${listing.genderPolicy}`)} · ${t(`meals.${listing.meals}`)}`}</span>
          </p>
          <h1 className="text-title-1 font-bold text-balance text-foreground">{listing.name}</h1>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {listing.verified ? (
              <Badge variant="neem" className="px-3 py-1 text-xs font-semibold">
                <ShieldCheck aria-hidden="true" className="size-3.5" />
                {t("verified")}
              </Badge>
            ) : (
              <Badge variant="outline" className="bg-card px-3 py-1 text-xs">
                {t("notVerified")}
              </Badge>
            )}
            <span className="rounded-full border border-marigold-border bg-marigold-soft px-3 py-1 text-xs font-medium text-marigold-soft-foreground">
              {t("runBy", { business: listing.ownerBusinessName })}
            </span>
          </div>
        </div>
        <Link
          href={visit}
          className={cn(
            buttonVariants({ size: "lg", shape: "pill" }),
            "relative shrink-0 self-start shadow-md sm:self-auto",
          )}
        >
          {t("bookVisit")}
        </Link>
      </header>

      <Gallery listing={listing} />
      <Rooms categories={listing.categories} calendar={calendar} />
      {listing.categories.length === 0 ? null : (
        <CheckPrice
          categories={listing.categories}
          stay={calendar?.stayMonths ?? DEFAULT_STAY}
          visit={onSpotVisit}
        />
      )}
      <Safety listing={listing} />

      {listing.amenities.length === 0 && listing.houseRules.length === 0 ? null : (
        <div className="grid gap-6 md:grid-cols-2">
          {listing.amenities.length === 0 ? null : (
            <Card
              asChild
              variant="marigold"
              className="relative space-y-4 overflow-hidden rounded-3xl p-6"
            >
              <section aria-labelledby="amenities-title">
                <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1.5 bg-marigold" />
                <h2 id="amenities-title" className="text-title-3 font-semibold text-foreground">
                  {t("amenities")}
                </h2>
                <ul className="flex flex-wrap gap-2">
                  {listing.amenities.map((amenity) => (
                    <li
                      key={amenity.slug}
                      className="rounded-full border border-marigold-border bg-card px-3.5 py-1.5 text-sm font-medium text-foreground shadow-2xs"
                    >
                      {amenity.name}
                    </li>
                  ))}
                </ul>
              </section>
            </Card>
          )}
          {listing.houseRules.length === 0 ? null : (
            <Card
              asChild
              variant="ember"
              className="relative space-y-4 overflow-hidden rounded-3xl p-6"
            >
              <section aria-labelledby="rules-title">
                <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1.5 bg-ember" />
                <h2 id="rules-title" className="text-title-3 font-semibold text-foreground">
                  {t("rules")}
                </h2>
                <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-foreground">
                  {listing.houseRules.map((rule) => (
                    <li key={rule}>{rule}</li>
                  ))}
                </ul>
              </section>
            </Card>
          )}
        </div>
      )}

      {listing.description === "" ? null : (
        <Card
          asChild
          variant="warm"
          className="relative space-y-3 overflow-hidden rounded-3xl p-6 sm:p-8"
        >
          <section aria-labelledby="about-title">
            <ArchWatermark
              tone="marigold"
              className="absolute -right-4 -bottom-4 size-36 opacity-15"
            />
            <h2 id="about-title" className="relative text-title-3 font-semibold text-foreground">
              {t("about")}
            </h2>
            <p className="relative max-w-prose leading-7 whitespace-pre-line text-foreground">
              {listing.description}
            </p>
          </section>
        </Card>
      )}

      <Location listing={listing} />

      <Card
        variant="ember"
        className="relative flex flex-wrap items-center justify-between gap-4 overflow-hidden rounded-3xl p-6 sm:p-8"
      >
        <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1.5 bg-ember" />
        <ArchWatermark tone="ember" className="absolute -right-4 -bottom-4 size-32 opacity-15" />
        <p className="relative text-sm font-semibold text-foreground">
          {t("runBy", { business: listing.ownerBusinessName })}
        </p>
        <Link
          href={visit}
          className={cn(buttonVariants({ size: "lg", shape: "pill" }), "relative shadow-md")}
        >
          {t("bookVisit")}
        </Link>
      </Card>
    </div>
  );
}

async function Gallery({ listing }: { listing: PublicListing }) {
  const t = await getTranslations("Pg.gallery");
  const photos = listing.media.filter((media) => media.contentType.startsWith("image/"));
  const videos = listing.media.filter((media) => media.contentType.startsWith("video/"));
  return (
    <section aria-labelledby="gallery-title" className="space-y-4">
      <h2 id="gallery-title" className="sr-only">
        {t("title")}
      </h2>
      {photos.length === 0 ? (
        <Card
          variant="warm"
          className="relative overflow-hidden rounded-3xl border-dashed p-8 text-center text-muted-foreground"
        >
          <ListingPlaceholderArt className="mx-auto mb-4 h-36 max-w-md rounded-2xl border border-marigold-border/60" />
          <p className="font-medium text-foreground">{t("none")}</p>
        </Card>
      ) : (
        <ul className="grid grid-cols-2 gap-2.5 overflow-hidden rounded-2xl sm:grid-cols-4 sm:gap-3 sm:rounded-3xl">
          {photos.map((media, index) => (
            <li
              key={media.id}
              className={cn(
                "group relative overflow-hidden rounded-xl bg-muted sm:rounded-none",
                index === 0 && "col-span-2 row-span-2",
              )}
            >
              <Photo
                media={media}
                alt={t("photo", { number: index + 1, name: listing.name })}
                sizes={
                  index === 0 ? "(min-width: 1024px) 620px, 100vw" : "(min-width: 640px) 25vw, 50vw"
                }
                first={index === 0}
                className="aspect-[3/2] h-full w-full object-cover transition-transform duration-(--duration-slow) ease-standard group-hover:scale-[1.02] motion-reduce:transition-none"
              />
              {media.verifiedCapture ? (
                <Badge variant="overlay" className="absolute bottom-3 left-3 shadow-xs">
                  <ShieldCheck aria-hidden="true" className="size-3 text-primary" />
                  {t("verifiedPhoto")}
                </Badge>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {videos.map((media) => {
        const source = media.renditions.find((rendition) => rendition.contentType === "video/mp4");
        const poster = media.renditions.find(
          (rendition) => rendition.name === "gallery" && rendition.contentType === "image/webp",
        );
        if (source === undefined) return null;
        return (
          <video
            key={media.id}
            controls
            preload="none"
            poster={poster?.url}
            aria-label={t("video", { name: listing.name })}
            className="w-full overflow-hidden rounded-2xl border bg-muted shadow-xs"
          >
            <source src={source.url} type="video/mp4" />
          </video>
        );
      })}
    </section>
  );
}

/** The rent a quote would say now for a category: its calendar's first week, else the listed. */
function currentRent(calendar: PriceCalendar | null): (category: Category) => number {
  const soonest = new Map(
    (calendar?.rooms ?? []).flatMap((room) =>
      room.weeks[0] === undefined ? [] : [[room.roomCategory, room.weeks[0].monthlyRentPaise]],
    ),
  );
  return (category) => soonest.get(category.id) ?? category.baseRentPaise;
}

const roomAccentBars = ["bg-primary", "bg-marigold", "bg-dusk", "bg-ember"] as const;

async function Rooms({
  categories,
  calendar,
}: {
  categories: Category[];
  calendar: PriceCalendar | null;
}) {
  const t = await getTranslations("Pg.rooms");
  const format = await getFormatter();
  const rentOf = currentRent(calendar);
  const day = (iso: string) =>
    format.dateTime(new Date(`${iso}T00:00:00+05:30`), {
      day: "numeric",
      month: "short",
      timeZone: "Asia/Kolkata",
    });
  return (
    <section aria-labelledby="rooms-title" className="space-y-5">
      <div className="space-y-1.5">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="h-6 w-1.5 rounded-full bg-primary" />
          <h2 id="rooms-title" className="text-title-2 font-bold text-foreground">
            {t("title")}
          </h2>
        </div>
        <p className="max-w-prose text-sm text-muted-foreground sm:text-base">{t("intro")}</p>
      </div>
      {categories.length === 0 ? (
        <Card variant="warm" className="p-6 text-muted-foreground">
          <p>{t("none")}</p>
        </Card>
      ) : (
        <ul className="grid gap-5 md:grid-cols-2">
          {categories.map((category, index) => (
            <li
              key={category.id}
              className="relative flex flex-col justify-between gap-5 overflow-hidden rounded-3xl border bg-card p-6 text-card-foreground shadow-sm"
            >
              <span
                aria-hidden="true"
                className={`absolute inset-x-0 top-0 h-1.5 ${roomAccentBars[index % roomAccentBars.length] ?? "bg-primary"}`}
              />
              <div className="space-y-4 pt-1">
                <div className="space-y-1">
                  <h3 className="font-display text-lg font-semibold tracking-tight text-foreground">
                    {category.label}
                  </h3>
                  <p className="text-sm font-medium text-muted-foreground">
                    {[
                      t(`sharing.${category.occupancy}`),
                      category.ac ? t("ac") : null,
                      category.attachedBath ? t("attachedBath") : null,
                      category.balcony ? t("balcony") : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <RoomPrice
                  rent={rentOf(category)}
                  room={calendar?.rooms.find((room) => room.roomCategory === category.id)}
                  stay={calendar?.stayMonths}
                  day={day}
                />
              </div>
              <div className="space-y-3 rounded-2xl border border-marigold-border/70 bg-surface-warm p-4 text-sm">
                <p className="font-semibold text-foreground tabular-nums">
                  {t("deposit", { amount: formatINR(category.securityDepositPaise) })}
                </p>
                <Separator />
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold tracking-wider text-marigold-soft-foreground uppercase">
                    {t("charges")}
                  </p>
                  {category.mandatoryCharges.length === 0 ? (
                    <p className="text-muted-foreground">{t("noCharges")}</p>
                  ) : (
                    <>
                      <ul className="list-disc space-y-1 pl-5 text-foreground tabular-nums">
                        {category.mandatoryCharges.map((charge) => (
                          <li key={`${charge.type}-${charge.label}`}>{chargeText(charge, t)}</li>
                        ))}
                      </ul>
                      <p className="pt-1 text-xs font-medium text-muted-foreground tabular-nums">
                        {t("totals", {
                          monthly: formatINR(category.monthlyChargesPaise),
                          once: formatINR(category.oneTimeChargesPaise),
                        })}
                      </p>
                    </>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const STAYS = [1, 3, 6, 9, 11, 12, 18, 24] as const;

/**
 * A room's price as a quote would say it now, fixed for the stay; where the calendar shows the
 * price changing, when; and scarcity, only from its free beds (CLAUDE.md rule 7, ADR 0040).
 */
async function RoomPrice({
  rent,
  room,
  stay,
  day,
}: {
  rent: number;
  room: PriceCalendar["rooms"][number] | undefined;
  stay: number | undefined;
  day: (iso: string) => string;
}) {
  const t = await getTranslations("Pg.rooms");
  const stretches = room === undefined ? [] : priceStretches(room.weeks);
  const changes =
    stretches.length < 2
      ? null
      : stretches
          .map((stretch, index) =>
            index === 0
              ? t("moveInBy", {
                  date: day(stretch.last),
                  amount: formatINR(stretch.monthlyRentPaise),
                })
              : t("fromDate", {
                  date: day(stretch.first),
                  amount: formatINR(stretch.monthlyRentPaise),
                }),
          )
          .join(" · ");
  const scarce = room === undefined ? null : scarceBeds(room.bedsFree);
  return (
    <div className="space-y-2.5">
      <p className="inline-block rounded-xl border border-primary-border bg-primary-soft px-3.5 py-1.5 font-display text-2xl font-bold tracking-tight text-primary-soft-foreground tabular-nums">
        {t("rent", { amount: formatINR(rent) })}
      </p>
      {room === undefined || stay === undefined ? null : (
        <p className="text-xs text-muted-foreground">{t("headlineNote", { months: stay })}</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="neem" className="px-3 py-1 text-xs font-semibold">
          <Check aria-hidden="true" className="size-3.5" />
          {t("fixedForStay")}
        </Badge>
        {scarce === null ? null : (
          <Badge variant="marigold" className="px-3 py-1 text-xs font-semibold">
            {t("bedsLeft", { count: scarce })}
          </Badge>
        )}
      </div>
      {changes === null ? null : (
        <p className="rounded-lg border border-dusk-border bg-dusk-soft px-3 py-1.5 text-xs font-medium text-dusk-soft-foreground tabular-nums">
          {changes}
        </p>
      )}
    </div>
  );
}

/**
 * A student's own price for a room, move-in and stay: a quote, with its full breakdown; and, at
 * their visit, reserving the bed at that price on the spot.
 */
async function CheckPrice({
  categories,
  stay,
  visit,
}: {
  categories: Category[];
  stay: number;
  visit: string | null;
}) {
  const t = await getTranslations("Pg.quote");
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const errors = [
    "generic",
    "QUOTE_INVALID",
    "RATE_LIMITED",
    "PRICING_CONFIG_ERROR",
    "API_UNREACHABLE",
  ] as const;
  return (
    <section
      aria-labelledby="quote-title"
      className="relative space-y-5 overflow-hidden rounded-3xl border border-dusk-border bg-dusk-soft p-6 shadow-sm sm:p-8"
    >
      <span
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-1.5"
        style={{
          backgroundImage:
            "linear-gradient(90deg, var(--dusk) 0%, var(--primary) 40%, var(--marigold) 75%, var(--ember) 100%)",
        }}
      />
      <ArchWatermark tone="dusk" className="absolute -right-6 -bottom-6 size-44 opacity-15" />
      <div className="relative space-y-1.5">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="grid size-10 place-items-center rounded-xl bg-card text-dusk-soft-foreground shadow-2xs ring-1 ring-dusk-border"
          >
            <Sparkles className="size-5" />
          </span>
          <h2 id="quote-title" className="text-title-2 font-bold text-foreground">
            {t("title")}
          </h2>
        </div>
        <p className="max-w-prose text-sm text-foreground sm:text-base">
          {visit === null ? t("intro") : t("atYourVisit")}
        </p>
      </div>
      <QuoteCheckerNear
        rooms={categories.map((category) => ({ id: category.id, label: category.label }))}
        stays={STAYS.map((months) => ({ value: months, label: t("months", { count: months }) }))}
        defaultStay={stay}
        today={today}
        visit={visit}
        text={{
          room: t("room"),
          chooseRoom: t("chooseRoom"),
          moveIn: t("moveIn"),
          stay: t("stay"),
          submit: t("submit"),
          checking: t("checking"),
          needRoom: t("needRoom"),
          needDate: t("needDate"),
          monthly: t.raw("monthly") as string,
          token: t.raw("token") as string,
          dueAtMoveIn: t.raw("dueAtMoveIn") as string,
          deposit: t.raw("deposit") as string,
          charges: t.raw("charges") as string,
          noCharges: t("noCharges"),
          validUntil: t.raw("validUntil") as string,
          bookingSoon: t("bookingSoon"),
          errors: Object.fromEntries(errors.map((code) => [code, t(`errors.${code}`)])),
          reserve: {
            note: t("reserve.note"),
            submit: t("reserve.submit"),
            reserving: t("reserve.reserving"),
            errors: Object.fromEntries(
              RESERVE_ERRORS.map((code) => [code, t(`reserve.errors.${code}`)]),
            ),
          },
        }}
      />
    </section>
  );
}

function chargeText(
  charge: Charge,
  t: Awaited<ReturnType<typeof getTranslations<"Pg.rooms">>>,
): string {
  switch (charge.type) {
    case "monthly":
      return t("monthly", { label: charge.label, amount: formatINR(charge.amountPaise) });
    case "metered":
      return t("metered", {
        label: charge.label,
        rate: formatINR(charge.ratePaise),
        unit: charge.unit,
        estimate: formatINR(charge.monthlyEstimatePaise),
      });
    case "oneTime":
      return t("oneTime", { label: charge.label, amount: formatINR(charge.amountPaise) });
  }
}

async function Safety({ listing }: { listing: PublicListing }) {
  const t = await getTranslations("Pg.safety");
  const format = await getFormatter();
  const { safety } = listing;
  const checks =
    safety === null
      ? []
      : ([
          [t("fireExtinguishers"), safety.fireExtinguishers],
          [t("cctv"), safety.cctv],
          [t("warden"), safety.warden],
        ] as const);
  return (
    <Card
      asChild
      variant="neem"
      className="relative space-y-5 overflow-hidden rounded-3xl p-6 sm:p-8"
    >
      <section aria-labelledby="safety-title">
        <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1.5 bg-neem" />
        <ArchWatermark tone="neem" className="absolute -right-6 -bottom-6 size-44 opacity-15" />
        <div className="relative flex items-center gap-2.5">
          <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-card text-neem-soft-foreground shadow-2xs ring-1 ring-neem-border">
            <ShieldCheck aria-hidden="true" className="size-5" />
          </div>
          <h2 id="safety-title" className="text-title-2 font-bold text-foreground">
            {t("title")}
          </h2>
        </div>
        {safety === null ? (
          <p className="relative text-muted-foreground">{t("notChecked")}</p>
        ) : (
          <div className="relative space-y-5">
            <p className="rounded-xl border border-neem-border bg-card px-4 py-3 text-sm font-semibold text-neem-soft-foreground shadow-2xs">
              {t("checked", {
                date: format.dateTime(new Date(`${safety.verifiedOn}T00:00:00+05:30`), {
                  dateStyle: "long",
                }),
              })}
            </p>
            <ul className="grid gap-3 sm:grid-cols-2">
              <li className="flex items-center gap-2.5 rounded-xl border border-neem-border bg-card px-4 py-3 text-sm font-medium text-foreground shadow-2xs">
                <Check aria-hidden="true" className="size-4 shrink-0 text-neem-soft-foreground" />
                <span>{t("exits", { count: safety.exits })}</span>
              </li>
              {checks.map(([label, present]) => (
                <li
                  key={label}
                  className="flex items-center gap-2.5 rounded-xl border border-neem-border bg-card px-4 py-3 text-sm text-foreground shadow-2xs"
                >
                  {present ? (
                    <Check
                      aria-hidden="true"
                      className="size-4 shrink-0 text-neem-soft-foreground"
                    />
                  ) : (
                    <X aria-hidden="true" className="size-4 shrink-0 text-destructive" />
                  )}
                  <span>
                    {label}: {present ? t("yes") : t("no")}
                  </span>
                </li>
              ))}
            </ul>
            <div className="space-y-2">
              <p className="text-sm font-semibold text-foreground">{t("womenSafety")}</p>
              {safety.womenSafety.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("womenSafetyNone")}</p>
              ) : (
                <ul className="flex flex-wrap gap-2">
                  {safety.womenSafety.map((feature) => (
                    <li
                      key={feature}
                      className="inline-flex items-center gap-1.5 rounded-full border border-marigold-border bg-marigold-soft px-3.5 py-1.5 text-sm font-medium text-marigold-soft-foreground shadow-2xs"
                    >
                      <Check aria-hidden="true" className="size-3.5" />
                      {t(`feature.${feature}`)}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
        <Separator />
        <ul className="relative flex flex-wrap gap-x-6 gap-y-2 text-sm font-medium text-foreground">
          <li>{t(`licence.${listing.licenceStatus}`)}</li>
          <li>{t(`society.${listing.societyPermission}`)}</li>
        </ul>
      </section>
    </Card>
  );
}

async function Location({ listing }: { listing: PublicListing }) {
  const t = await getTranslations("Pg");
  return (
    <section aria-labelledby="location-title" className="space-y-5">
      <div className="space-y-1.5">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="h-6 w-1.5 rounded-full bg-ember" />
          <h2 id="location-title" className="text-title-2 font-bold text-foreground">
            {t("location.title")}
          </h2>
        </div>
        <p className="max-w-prose text-sm text-muted-foreground sm:text-base">
          {t("location.approximate", { locality: listing.locality.name })}
        </p>
      </div>
      <LocationMap
        center={listing.displayLocation}
        radiusM={APPROXIMATE_RADIUS_M}
        text={{
          map: t("location.map"),
          zoomIn: t("map.zoomIn"),
          zoomOut: t("map.zoomOut"),
          credits: t("map.credits"),
          twoFingers: t("map.twoFingers"),
          ctrlScroll: t("map.ctrlScroll"),
          cmdScroll: t("map.cmdScroll"),
          failed: t("map.failed"),
        }}
      />
      <div className="grid gap-5 sm:grid-cols-2">
        {[
          {
            key: "campuses",
            variant: "dusk" as const,
            title: t("location.campuses"),
            places: listing.campusesNearby,
          },
          {
            key: "stations",
            variant: "ink" as const,
            title: t("location.stations"),
            places: listing.stationsNearby,
          },
        ].map((group) =>
          group.places.length === 0 ? null : (
            <Card key={group.key} variant={group.variant} className="space-y-2.5 rounded-3xl p-6">
              <h3 className="font-display font-semibold text-foreground">{group.title}</h3>
              <ul className="space-y-1.5 text-sm font-medium text-foreground tabular-nums">
                {group.places.map((place) => (
                  <li key={place.slug}>
                    {t("location.distance", {
                      place: place.name,
                      distance: formatDistance(place.distanceM),
                    })}
                  </li>
                ))}
              </ul>
            </Card>
          ),
        )}
      </div>
    </section>
  );
}
