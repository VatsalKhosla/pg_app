import type { Schemas } from "@pg-platform/api-client";
import { Check, MapPin, ShieldCheck, X } from "lucide-react";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";
import { ViewTransition } from "react";

import { ListingPlaceholderArt } from "@/components/brand/editorial-art";
import { LocationMap } from "@/components/map/location-map";
import { Photo } from "@/components/pg/photo";
import { QuoteCheckerNear } from "@/components/pg/quote-checker-near";
import { RoomIllustration } from "@/components/pg/room-illustration";
import { ViewCounter } from "@/components/pg/view-counter";
import { JsonLd } from "@/components/seo/json-ld";
import { TrackView } from "@/components/system/track-view";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
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
  const from = listing.categories.length === 0 ? null : Math.min(...listing.categories.map(rentOf));
  const t = await getTranslations("Pg");
  const tLanding = await getTranslations("Landing");
  const visit = `/pg/${slug}/visit` as Route;
  const absolute = (path: string) => new URL(path, publicEnv.siteUrl).toString();
  const localityPath = `/pg-in/${listing.locality.slug}`;

  return (
    <div className="mx-auto w-full max-w-page px-gutter pt-6 pb-32 sm:pt-10 lg:pb-20">
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
      <header className="space-y-3">
        <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-muted-foreground">
          <MapPin aria-hidden="true" className="size-4" />
          <Link
            href={localityPath as Route}
            className="inline-flex min-h-6 items-center rounded font-semibold text-foreground underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {listing.locality.name}
          </Link>
          <span>{`· ${t(`genderShort.${listing.genderPolicy}`)} · ${t(`meals.${listing.meals}`)}`}</span>
        </p>
        <h1 className="max-w-[22ch] text-display font-medium text-foreground">{listing.name}</h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          {listing.verified ? (
            <Badge variant="neem" className="px-3 py-1 text-xs font-semibold">
              <ShieldCheck aria-hidden="true" className="size-3.5" />
              {t("verified")}
            </Badge>
          ) : (
            <Badge variant="outline" className="px-3 py-1 text-xs">
              {t("notVerified")}
            </Badge>
          )}
          <span className="text-muted-foreground">
            {t("runBy", { business: listing.ownerBusinessName })}
          </span>
        </div>
      </header>

      <Gallery listing={listing} />

      <div className="mt-10 grid gap-12 lg:mt-14 lg:grid-cols-[minmax(0,1fr)_23rem] lg:gap-x-14 xl:grid-cols-[minmax(0,1fr)_25rem] xl:gap-x-20">
        <div className="min-w-0 lg:col-start-1">
          <Rooms categories={listing.categories} calendar={calendar} />
        </div>

        <div className="min-w-0 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <div className="space-y-5 rounded-[2rem] border bg-card p-6 shadow-lg sm:p-7 lg:sticky lg:top-24 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto">
            {from === null ? null : (
              <div>
                <p className="text-title-2 font-semibold tabular-nums">
                  {t("fromPrice", { amount: formatINR(from) })}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">{t("fromNote")}</p>
              </div>
            )}
            <Link
              href={visit}
              className={buttonVariants({
                variant: "sun",
                size: "lg",
                shape: "pill",
                className: "w-full",
              })}
            >
              {t("bookVisit")}
            </Link>
            {listing.categories.length === 0 ? null : (
              <CheckPrice
                categories={listing.categories}
                stay={calendar?.stayMonths ?? DEFAULT_STAY}
                visit={onSpotVisit}
              />
            )}
          </div>
        </div>

        <div className="min-w-0 space-y-14 lg:col-start-1">
          <Safety listing={listing} />

          {listing.amenities.length === 0 ? null : (
            <section aria-labelledby="amenities-title">
              <h2 id="amenities-title" className="text-title-2 font-medium">
                {t("amenities")}
              </h2>
              <ul className="mt-4 flex flex-wrap gap-2">
                {listing.amenities.map((amenity) => (
                  <li key={amenity.slug} className="rounded-full border px-3.5 py-1.5 text-sm">
                    {amenity.name}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {listing.houseRules.length === 0 ? null : (
            <section aria-labelledby="rules-title">
              <h2 id="rules-title" className="text-title-2 font-medium">
                {t("rules")}
              </h2>
              <ul className="mt-4 max-w-prose list-disc space-y-2 pl-5 leading-relaxed">
                {listing.houseRules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
            </section>
          )}

          {listing.description === "" ? null : (
            <section aria-labelledby="about-title">
              <h2 id="about-title" className="text-title-2 font-medium">
                {t("about")}
              </h2>
              <p className="mt-3 max-w-prose leading-7 whitespace-pre-line">
                {listing.description}
              </p>
            </section>
          )}

          <Location listing={listing} />
        </div>
      </div>

      {from === null ? null : (
        <div className="glass fixed inset-x-0 bottom-0 z-30 flex items-center justify-between gap-3 border-x-0 border-b-0 px-gutter pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:hidden">
          <p className="text-lg leading-tight font-semibold tabular-nums">
            {t("fromPrice", { amount: formatINR(from) })}
          </p>
          <Link
            href={visit}
            className={buttonVariants({ variant: "sun", shape: "pill", className: "shrink-0" })}
          >
            {t("bookVisit")}
          </Link>
        </div>
      )}
    </div>
  );
}

/** Where a photo sits in the desktop's mosaic, so any number of photos fills it without a hole. */
function mosaicCell(index: number, count: number): string | undefined {
  const lead = "lg:col-span-2 lg:row-span-2 lg:rounded-[2rem]";
  if (count === 1) return "lg:col-span-4 lg:rounded-[2rem]";
  if (count === 2) return lead;
  if (index === 0) return lead;
  if (count === 3) return "lg:row-span-2";
  if (count === 4 && index === 3) return "lg:col-span-2";
  return undefined;
}

async function Gallery({ listing }: { listing: PublicListing }) {
  const t = await getTranslations("Pg.gallery");
  const photos = listing.media.filter((media) => media.contentType.startsWith("image/"));
  const videos = listing.media.filter((media) => media.contentType.startsWith("video/"));
  return (
    <section aria-labelledby="gallery-title" className="mt-6 space-y-4 sm:mt-8">
      <h2 id="gallery-title" className="sr-only">
        {t("title")}
      </h2>
      {photos.length === 0 ? (
        <div className="overflow-hidden rounded-[2rem] bg-surface-warm p-8 text-center">
          <ListingPlaceholderArt className="mx-auto mb-4 h-36 max-w-md rounded-2xl" />
          <p className="font-medium text-foreground">{t("none")}</p>
        </div>
      ) : (
        <ul className="-mx-gutter flex snap-x snap-mandatory scroll-px-gutter gap-2.5 overflow-x-auto px-gutter [scrollbar-width:none] sm:mx-0 sm:px-0 lg:grid lg:grid-cols-4 lg:overflow-visible">
          {photos.map((media, index) => (
            <li
              key={media.id}
              className={cn(
                "group relative w-[86%] shrink-0 snap-start overflow-hidden rounded-3xl bg-muted sm:w-[60%] lg:w-auto lg:rounded-2xl",
                mosaicCell(index, photos.length),
              )}
            >
              {index === 0 ? (
                <ViewTransition name={`pg-photo-${listing.id}`}>
                  <Photo
                    media={media}
                    alt={t("photo", { number: index + 1, name: listing.name })}
                    sizes="(min-width: 1024px) 640px, 86vw"
                    first
                    className="aspect-4/3 h-full w-full object-cover"
                  />
                </ViewTransition>
              ) : (
                <Photo
                  media={media}
                  alt={t("photo", { number: index + 1, name: listing.name })}
                  sizes="(min-width: 1024px) 310px, 86vw"
                  className="aspect-4/3 h-full w-full object-cover"
                />
              )}
              {media.verifiedCapture ? (
                <Badge variant="overlay" className="absolute bottom-3 left-3 shadow-xs">
                  <ShieldCheck aria-hidden="true" className="size-3 text-neem" />
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
    <section aria-labelledby="rooms-title">
      <h2 id="rooms-title" className="text-title-1 font-medium">
        {t("title")}
      </h2>
      <p className="mt-2 max-w-prose text-muted-foreground">{t("intro")}</p>
      {categories.length === 0 ? (
        <p className="mt-6 text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="mt-4 divide-y">
          {categories.map((category) => (
            <li
              key={category.id}
              className="grid gap-5 py-7 sm:grid-cols-[10.5rem_minmax(0,1fr)] sm:gap-8"
            >
              <RoomIllustration
                occupancy={category.occupancy}
                ac={category.ac}
                attachedBath={category.attachedBath}
                balcony={category.balcony}
                caption={t("illustration")}
              />
              <div className="min-w-0 space-y-4">
                <div className="space-y-1">
                  <h3 className="text-title-3 font-medium text-foreground">{category.label}</h3>
                  <p className="text-sm text-muted-foreground">
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
                <div className="space-y-2 text-sm">
                  <p className="font-semibold text-foreground tabular-nums">
                    {t("deposit", { amount: formatINR(category.securityDepositPaise) })}
                  </p>
                  <div className="space-y-1">
                    <p className="font-medium text-foreground">{t("charges")}</p>
                    {category.mandatoryCharges.length === 0 ? (
                      <p className="text-muted-foreground">{t("noCharges")}</p>
                    ) : (
                      <>
                        <ul className="list-disc space-y-1 pl-5 text-foreground tabular-nums">
                          {category.mandatoryCharges.map((charge) => (
                            <li key={`${charge.type}-${charge.label}`}>{chargeText(charge, t)}</li>
                          ))}
                        </ul>
                        <p className="pt-1 text-muted-foreground tabular-nums">
                          {t("totals", {
                            monthly: formatINR(category.monthlyChargesPaise),
                            once: formatINR(category.oneTimeChargesPaise),
                          })}
                        </p>
                      </>
                    )}
                  </div>
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
      <p className="text-title-2 font-semibold text-foreground tabular-nums">
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
        <p className="text-sm text-muted-foreground tabular-nums">{changes}</p>
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
    <section aria-labelledby="quote-title" className="space-y-3 border-t pt-5">
      <div className="space-y-1">
        <h2 id="quote-title" className="text-title-3 font-medium text-foreground">
          {t("title")}
        </h2>
        <p className="text-sm text-muted-foreground">
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
    <section
      aria-labelledby="safety-title"
      className="space-y-5 rounded-[2rem] bg-neem-soft p-6 text-neem-soft-foreground sm:p-8"
    >
      <h2 id="safety-title" className="text-title-2 font-medium">
        {t("title")}
      </h2>
      {safety === null ? (
        <p>{t("notChecked")}</p>
      ) : (
        <div className="space-y-5">
          <p className="font-semibold">
            {t("checked", {
              date: format.dateTime(new Date(`${safety.verifiedOn}T00:00:00+05:30`), {
                dateStyle: "long",
              }),
            })}
          </p>
          <ul className="grid gap-2.5 sm:grid-cols-2">
            <li className="flex items-center gap-2.5">
              <Check aria-hidden="true" className="size-4 shrink-0" />
              <span>{t("exits", { count: safety.exits })}</span>
            </li>
            {checks.map(([label, present]) => (
              <li key={label} className="flex items-center gap-2.5">
                {present ? (
                  <Check aria-hidden="true" className="size-4 shrink-0" />
                ) : (
                  <X aria-hidden="true" className="size-4 shrink-0" />
                )}
                <span>
                  {label}: {present ? t("yes") : t("no")}
                </span>
              </li>
            ))}
          </ul>
          <div className="space-y-2">
            <p className="font-semibold">{t("womenSafety")}</p>
            {safety.womenSafety.length === 0 ? (
              <p>{t("womenSafetyNone")}</p>
            ) : (
              <ul className="grid gap-2.5 sm:grid-cols-2">
                {safety.womenSafety.map((feature) => (
                  <li key={feature} className="flex items-center gap-2.5">
                    <Check aria-hidden="true" className="size-4 shrink-0" />
                    {t(`feature.${feature}`)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      <ul className="flex flex-wrap gap-x-6 gap-y-2 border-t border-neem-border pt-4 text-sm font-medium">
        <li>{t(`licence.${listing.licenceStatus}`)}</li>
        <li>{t(`society.${listing.societyPermission}`)}</li>
      </ul>
    </section>
  );
}

// A person walks about 80 metres a minute; distances here are straight lines, so it's an estimate.
const WALK_M_PER_MINUTE = 80;
// The commute lines share one scale, so distances compare at a glance.
const COMMUTE_SCALE_M = 3_000;

function walkMinutes(distanceM: number): number {
  return Math.max(1, Math.ceil(distanceM / WALK_M_PER_MINUTE));
}

function commuteWidth(distanceM: number): string {
  const share = Math.min(1, Math.max(0.06, distanceM / COMMUTE_SCALE_M));
  return String(Math.round(share * 100)) + "%";
}

async function Location({ listing }: { listing: PublicListing }) {
  const t = await getTranslations("Pg");
  return (
    <section aria-labelledby="location-title" className="space-y-5">
      <div className="space-y-2">
        <h2 id="location-title" className="text-title-2 font-medium text-foreground">
          {t("location.title")}
        </h2>
        <p className="max-w-prose text-muted-foreground">
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
      <div className="grid gap-8 sm:grid-cols-2 sm:gap-10">
        {[
          { key: "campuses", title: t("location.campuses"), places: listing.campusesNearby },
          { key: "stations", title: t("location.stations"), places: listing.stationsNearby },
        ].map((group) =>
          group.places.length === 0 ? null : (
            <div key={group.key}>
              <h3 className="font-sans text-base font-semibold text-foreground">{group.title}</h3>
              <ul className="mt-3 space-y-4 text-sm">
                {group.places.map((place) => (
                  <li key={place.slug}>
                    <p className="flex flex-wrap justify-between gap-x-3 tabular-nums">
                      <span className="font-medium text-foreground">
                        {t("location.distance", {
                          place: place.name,
                          distance: formatDistance(place.distanceM),
                        })}
                      </span>
                      <span className="text-muted-foreground">
                        {t("location.walk", { minutes: walkMinutes(place.distanceM) })}
                      </span>
                    </p>
                    <span aria-hidden="true" className="relative mt-2 block h-3">
                      <span className="absolute inset-x-0 top-[5px] h-0.5 rounded-full bg-border" />
                      <span
                        className="absolute top-[4px] left-0 h-1 rounded-full bg-sun"
                        style={{ width: commuteWidth(place.distanceM) }}
                      />
                      <span className="absolute top-0 left-0 size-3 rounded-full border-[3px] border-primary bg-background" />
                      <span
                        className="absolute top-0 size-3 -translate-x-full rounded-full bg-primary"
                        style={{ left: commuteWidth(place.distanceM) }}
                      />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ),
        )}
      </div>
      <p className="text-sm text-muted-foreground">{t("location.straightLine")}</p>
    </section>
  );
}
