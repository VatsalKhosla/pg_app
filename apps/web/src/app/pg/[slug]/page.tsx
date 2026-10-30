import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";
import { Check, ShieldCheck, X } from "lucide-react";

import { LocationMap } from "@/components/map/location-map";
import { Photo } from "@/components/pg/photo";
import { JsonLd } from "@/components/seo/json-ld";
import { buttonVariants } from "@/components/ui/button";
import { TrackView } from "@/components/system/track-view";
import { publicEnv } from "@/config/env";
import { QuoteChecker } from "@/components/pg/quote-checker";
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
export default async function PgPage({ params }: PageProps<"/pg/[slug]">) {
  const { slug } = await params;
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
    <div className="mx-auto w-full max-w-5xl space-y-10 px-4 py-8 sm:py-12">
      <TrackView event="pg_viewed" properties={{ slug }} />
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
        <p className="text-sm text-muted-foreground">
          <Link
            href={localityPath as Route}
            className="rounded underline underline-offset-4 outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {listing.locality.name}
          </Link>
          {` · ${t(`genderShort.${listing.genderPolicy}`)} · ${t(`meals.${listing.meals}`)}`}
        </p>
        <h1 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">
          {listing.name}
        </h1>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {listing.verified ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/40 bg-accent px-3 py-1 font-medium text-primary">
              <ShieldCheck aria-hidden="true" className="size-4" />
              {t("verified")}
            </span>
          ) : (
            <span className="rounded-full border px-3 py-1">{t("notVerified")}</span>
          )}
          <span className="text-muted-foreground">
            {t("runBy", { business: listing.ownerBusinessName })}
          </span>
        </div>
        <Link href={visit} className={cn(buttonVariants({ size: "lg" }), "mt-2")}>
          {t("bookVisit")}
        </Link>
      </header>

      <Gallery listing={listing} />
      <Rooms categories={listing.categories} calendar={calendar} />
      {listing.categories.length === 0 ? null : (
        <CheckPrice categories={listing.categories} stay={calendar?.stayMonths ?? DEFAULT_STAY} />
      )}
      <Safety listing={listing} />

      <div className="grid gap-10 md:grid-cols-2">
        {listing.amenities.length === 0 ? null : (
          <section aria-labelledby="amenities-title" className="space-y-3">
            <h2 id="amenities-title" className="text-xl font-semibold">
              {t("amenities")}
            </h2>
            <ul className="flex flex-wrap gap-2">
              {listing.amenities.map((amenity) => (
                <li key={amenity.slug} className="rounded-full border px-3 py-1 text-sm">
                  {amenity.name}
                </li>
              ))}
            </ul>
          </section>
        )}
        {listing.houseRules.length === 0 ? null : (
          <section aria-labelledby="rules-title" className="space-y-3">
            <h2 id="rules-title" className="text-xl font-semibold">
              {t("rules")}
            </h2>
            <ul className="list-disc space-y-1 pl-5">
              {listing.houseRules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {listing.description === "" ? null : (
        <section aria-labelledby="about-title" className="space-y-3">
          <h2 id="about-title" className="text-xl font-semibold">
            {t("about")}
          </h2>
          <p className="max-w-prose leading-7 whitespace-pre-line">{listing.description}</p>
        </section>
      )}

      <Location listing={listing} />

      <div className="border-t pt-6">
        <Link href={visit} className={buttonVariants({ size: "lg" })}>
          {t("bookVisit")}
        </Link>
      </div>
    </div>
  );
}

async function Gallery({ listing }: { listing: PublicListing }) {
  const t = await getTranslations("Pg.gallery");
  const photos = listing.media.filter((media) => media.contentType.startsWith("image/"));
  const videos = listing.media.filter((media) => media.contentType.startsWith("video/"));
  return (
    <section aria-labelledby="gallery-title" className="space-y-3">
      <h2 id="gallery-title" className="sr-only">
        {t("title")}
      </h2>
      {photos.length === 0 ? (
        <p className="rounded-md border border-dashed p-6 text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {photos.map((media, index) => (
            <li
              key={media.id}
              className={cn(
                "relative overflow-hidden rounded-md bg-muted",
                index === 0 && "col-span-2 row-span-2",
              )}
            >
              <Photo
                media={media}
                alt={t("photo", { number: index + 1, name: listing.name })}
                sizes={
                  index === 0 ? "(min-width: 1024px) 512px, 100vw" : "(min-width: 640px) 25vw, 50vw"
                }
                first={index === 0}
                className="aspect-[3/2] h-full w-full object-cover"
              />
              {media.verifiedCapture ? (
                <span className="absolute bottom-2 left-2 rounded bg-background/90 px-2 py-0.5 text-xs font-medium">
                  {t("verifiedPhoto")}
                </span>
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
            className="w-full rounded-md bg-muted"
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
    <section aria-labelledby="rooms-title" className="space-y-4">
      <div className="space-y-1">
        <h2 id="rooms-title" className="text-xl font-semibold">
          {t("title")}
        </h2>
        <p className="text-sm text-muted-foreground">{t("intro")}</p>
      </div>
      {categories.length === 0 ? (
        <p className="text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {categories.map((category) => (
            <li key={category.id} className="space-y-3 rounded-lg border p-4">
              <div className="space-y-1">
                <h3 className="font-semibold">{category.label}</h3>
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
              <p>{t("deposit", { amount: formatINR(category.securityDepositPaise) })}</p>
              <div className="space-y-1 text-sm">
                <p className="font-medium">{t("charges")}</p>
                {category.mandatoryCharges.length === 0 ? (
                  <p>{t("noCharges")}</p>
                ) : (
                  <>
                    <ul className="list-disc space-y-1 pl-5">
                      {category.mandatoryCharges.map((charge) => (
                        <li key={`${charge.type}-${charge.label}`}>{chargeText(charge, t)}</li>
                      ))}
                    </ul>
                    <p className="text-muted-foreground">
                      {t("totals", {
                        monthly: formatINR(category.monthlyChargesPaise),
                        once: formatINR(category.oneTimeChargesPaise),
                      })}
                    </p>
                  </>
                )}
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
    <div className="space-y-2">
      <p className="text-2xl font-bold">{t("rent", { amount: formatINR(rent) })}</p>
      {room === undefined || stay === undefined ? null : (
        <p className="text-sm text-muted-foreground">{t("headlineNote", { months: stay })}</p>
      )}
      <p className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium">
        <Check aria-hidden="true" className="size-4" />
        {t("fixedForStay")}
      </p>
      {changes === null ? null : <p className="text-sm">{changes}</p>}
      {scarce === null ? null : (
        <p className="text-sm font-semibold">{t("bedsLeft", { count: scarce })}</p>
      )}
    </div>
  );
}

/** A student's own price for a room, move-in and stay: a quote, with its full breakdown. */
async function CheckPrice({ categories, stay }: { categories: Category[]; stay: number }) {
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
    <section aria-labelledby="quote-title" className="space-y-4">
      <div className="space-y-1">
        <h2 id="quote-title" className="text-xl font-semibold">
          {t("title")}
        </h2>
        <p className="text-sm text-muted-foreground">{t("intro")}</p>
      </div>
      <QuoteChecker
        rooms={categories.map((category) => ({ id: category.id, label: category.label }))}
        stays={STAYS.map((months) => ({ value: months, label: t("months", { count: months }) }))}
        defaultStay={stay}
        today={today}
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
    <section aria-labelledby="safety-title" className="space-y-4">
      <h2 id="safety-title" className="text-xl font-semibold">
        {t("title")}
      </h2>
      {safety === null ? (
        <p className="text-muted-foreground">{t("notChecked")}</p>
      ) : (
        <div className="space-y-4">
          <p>
            {t("checked", {
              date: format.dateTime(new Date(`${safety.verifiedOn}T00:00:00+05:30`), {
                dateStyle: "long",
              }),
            })}
          </p>
          <ul className="grid gap-2 sm:grid-cols-2">
            <li>{t("exits", { count: safety.exits })}</li>
            {checks.map(([label, present]) => (
              <li key={label} className="flex items-center gap-2">
                {present ? (
                  <Check aria-hidden="true" className="size-4 text-primary" />
                ) : (
                  <X aria-hidden="true" className="size-4 text-destructive" />
                )}
                <span>
                  {label}: {present ? t("yes") : t("no")}
                </span>
              </li>
            ))}
          </ul>
          <div className="space-y-1">
            <p className="font-medium">{t("womenSafety")}</p>
            {safety.womenSafety.length === 0 ? (
              <p className="text-muted-foreground">{t("womenSafetyNone")}</p>
            ) : (
              <ul className="list-disc space-y-1 pl-5">
                {safety.womenSafety.map((feature) => (
                  <li key={feature}>{t(`feature.${feature}`)}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      <ul className="space-y-1 text-sm text-muted-foreground">
        <li>{t(`licence.${listing.licenceStatus}`)}</li>
        <li>{t(`society.${listing.societyPermission}`)}</li>
      </ul>
    </section>
  );
}

async function Location({ listing }: { listing: PublicListing }) {
  const t = await getTranslations("Pg");
  return (
    <section aria-labelledby="location-title" className="space-y-4">
      <h2 id="location-title" className="text-xl font-semibold">
        {t("location.title")}
      </h2>
      <p>{t("location.approximate", { locality: listing.locality.name })}</p>
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
      <div className="grid gap-6 sm:grid-cols-2">
        {[
          { key: "campuses", title: t("location.campuses"), places: listing.campusesNearby },
          { key: "stations", title: t("location.stations"), places: listing.stationsNearby },
        ].map((group) =>
          group.places.length === 0 ? null : (
            <div key={group.key} className="space-y-2">
              <h3 className="font-medium">{group.title}</h3>
              <ul className="space-y-1">
                {group.places.map((place) => (
                  <li key={place.slug}>
                    {t("location.distance", {
                      place: place.name,
                      distance: formatDistance(place.distanceM),
                    })}
                  </li>
                ))}
              </ul>
            </div>
          ),
        )}
      </div>
    </section>
  );
}
