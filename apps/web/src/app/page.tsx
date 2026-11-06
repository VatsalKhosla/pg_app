import { CalendarCheck, KeyRound, MapPinned, ShieldCheck } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { ArchWatermark, HeroCourtyardIllustration } from "@/components/brand/editorial-art";
import { homeSections } from "@/components/layout/navigation";
import { JsonLd } from "@/components/seo/json-ld";
import { ApiStatus, ApiStatusPending } from "@/components/system/api-status";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { brand } from "@/config/brand";
import { publicEnv } from "@/config/env";
import { getSearchPlaces, type SearchPlace } from "@/lib/api/public";
import { organizationJsonLd } from "@/lib/seo/json-ld";

const steps = [
  {
    key: "find",
    Icon: MapPinned,
    cardVariant: "teal",
    tone: "teal",
    iconClass: "bg-card text-primary-soft-foreground ring-1 ring-primary-border shadow-xs",
    numeralClass: "text-primary-soft-foreground",
    barClass: "bg-primary",
  },
  {
    key: "visit",
    Icon: CalendarCheck,
    cardVariant: "saffron",
    tone: "saffron",
    iconClass: "bg-card text-saffron-soft-foreground ring-1 ring-saffron-border shadow-xs",
    numeralClass: "text-saffron-soft-foreground",
    barClass: "bg-saffron",
  },
  {
    key: "reserve",
    Icon: ShieldCheck,
    cardVariant: "indigo",
    tone: "indigo",
    iconClass: "bg-card text-indigo-soft-foreground ring-1 ring-indigo-border shadow-xs",
    numeralClass: "text-indigo-soft-foreground",
    barClass: "bg-indigo",
  },
  {
    key: "moveIn",
    Icon: KeyRound,
    cardVariant: "coral",
    tone: "coral",
    iconClass: "bg-card text-coral-soft-foreground ring-1 ring-coral-border shadow-xs",
    numeralClass: "text-coral-soft-foreground",
    barClass: "bg-coral",
  },
] as const;

// Sections that the navigation links to: focusable, so a followed link can move focus here, and
// offset so the sticky header doesn't cover their headings.
const sectionClassName = "scroll-mt-24 outline-none focus-visible:ring-2 focus-visible:ring-ring";
// Places linked from the home page, of each kind: the ones with the most PGs.
const PLACES_SHOWN = 8;

const placeChipClasses =
  "inline-flex min-h-11 items-center rounded-full border border-input/80 bg-card px-4 py-2 text-sm font-medium text-foreground shadow-2xs transition-[background-color,border-color,color,transform,box-shadow] duration-(--duration-fast) ease-standard outline-none hover:-translate-y-0.5 hover:border-primary hover:bg-primary-soft hover:text-primary-soft-foreground hover:shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none motion-reduce:hover:translate-y-0";

/**
 * Links to the landing pages of the campuses and localities with the most PGs (step 3.6), for
 * people and search engines alike. Without the API there's nothing to link to, and the home page
 * stands without it.
 */
async function PopularPlaces() {
  let places: SearchPlace[];
  try {
    places = (await getSearchPlaces()).items;
  } catch {
    return null;
  }
  if (places.length === 0) return null;
  const t = await getTranslations("Home.places");
  const groups = [
    {
      title: t("campuses"),
      variant: "indigo" as const,
      tone: "indigo" as const,
      dotClass: "bg-indigo",
      items: places.filter((place) => place.kind === "campus").slice(0, PLACES_SHOWN),
      path: (slug: string) => `/pg-near/${slug}`,
    },
    {
      title: t("localities"),
      variant: "saffron" as const,
      tone: "saffron" as const,
      dotClass: "bg-saffron",
      items: places.filter((place) => place.kind === "locality").slice(0, PLACES_SHOWN),
      path: (slug: string) => `/pg-in/${slug}`,
    },
  ].filter((group) => group.items.length > 0);
  return (
    <section
      aria-labelledby="places-title"
      className="mx-auto w-full max-w-page px-gutter pb-section"
    >
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="h-6 w-1.5 rounded-full bg-coral" />
        <h2 id="places-title" className="text-title-1 font-bold tracking-tight">
          {t("title")}
        </h2>
      </div>
      <div className="mt-8 grid gap-6 md:grid-cols-2">
        {groups.map((group) => (
          <Card
            key={group.title}
            variant={group.variant}
            className="relative overflow-hidden rounded-3xl p-6 sm:p-8"
          >
            <ArchWatermark
              tone={group.tone}
              className="absolute -right-4 -bottom-4 size-32 opacity-15"
            />
            <div className="relative flex items-center gap-2.5">
              <span aria-hidden="true" className={`size-2.5 rounded-full ${group.dotClass}`} />
              <h3 className="text-title-3 font-semibold text-foreground">{group.title}</h3>
            </div>
            <ul className="relative mt-5 flex flex-wrap gap-2.5">
              {group.items.map((place) => (
                <li key={place.slug}>
                  <Link href={group.path(place.slug) as Route} className={placeChipClasses}>
                    {t("place", { name: place.name, count: place.listings })}
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </section>
  );
}

export default async function HomePage() {
  const t = await getTranslations("Home");
  const tBrand = await getTranslations("Brand");
  const absolute = (path: string) => new URL(path, publicEnv.siteUrl).toString();

  return (
    <>
      {/* For search engines: the business behind the site, with its icon as the logo. */}
      <JsonLd
        data={organizationJsonLd({
          name: brand.name,
          url: absolute("/"),
          logo: absolute("/icon/512"),
        })}
      />
      <section className="relative overflow-hidden border-b border-saffron-border/70 bg-surface-warm">
        <div className="relative mx-auto grid max-w-page items-center gap-10 px-gutter py-14 sm:py-20 lg:grid-cols-[1.1fr_0.9fr] lg:gap-12 lg:py-24">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="coral" className="gap-2 px-3.5 py-1 text-xs font-semibold shadow-2xs">
                <span aria-hidden className="size-2 rounded-full bg-coral" />
                {t("status")}
              </Badge>
              <span
                aria-hidden="true"
                className="inline-flex items-center gap-1.5 rounded-full border border-saffron-border bg-saffron-soft px-3 py-1 text-xs font-semibold text-saffron-soft-foreground"
              >
                <span className="size-1.5 rounded-full bg-saffron" />
                <span className="size-1.5 rounded-full bg-sage" />
                <span className="size-1.5 rounded-full bg-primary" />
              </span>
            </div>
            <h1 className="mt-6 max-w-2xl text-display font-bold tracking-tight text-foreground">
              {tBrand("tagline")}
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
              {t("intro")}
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3.5">
              <Link
                href="/search"
                className={buttonVariants({
                  size: "lg",
                  shape: "pill",
                  className: "shadow-lg",
                })}
              >
                <MapPinned aria-hidden="true" />
                {t("findCta")}
              </Link>
            </div>
            {/* Decorative hospitality color bar */}
            <div aria-hidden="true" className="mt-10 flex items-center gap-2">
              <span className="h-2 w-12 rounded-full bg-primary" />
              <span className="h-2 w-8 rounded-full bg-coral" />
              <span className="h-2 w-6 rounded-full bg-saffron" />
              <span className="h-2 w-5 rounded-full bg-sage" />
              <span className="h-2 w-4 rounded-full bg-indigo" />
            </div>
          </div>
          <HeroCourtyardIllustration />
        </div>
      </section>

      <section
        id={homeSections.howItWorks}
        tabIndex={-1}
        aria-labelledby="how-it-works-title"
        className={sectionClassName}
      >
        <div className="mx-auto max-w-page px-gutter py-section">
          <div className="flex items-center gap-3">
            <span aria-hidden="true" className="h-6 w-1.5 rounded-full bg-primary" />
            <h2 id="how-it-works-title" className="text-title-1 font-bold tracking-tight">
              {t("steps.title")}
            </h2>
          </div>
          <ol className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map(
              ({ key, Icon, cardVariant, tone, iconClass, numeralClass, barClass }, index) => (
                <Card
                  key={key}
                  asChild
                  variant={cardVariant}
                  className="relative justify-between gap-6 overflow-hidden rounded-3xl p-6 shadow-sm"
                >
                  <li>
                    <span
                      aria-hidden="true"
                      className={`absolute inset-x-0 top-0 h-1.5 ${barClass}`}
                    />
                    <ArchWatermark
                      tone={tone}
                      className="absolute -right-4 -bottom-4 size-28 opacity-15"
                    />
                    <div className="relative flex items-center justify-between gap-3 pt-1">
                      <span
                        aria-hidden
                        className={`grid size-12 place-items-center rounded-2xl ${iconClass}`}
                      >
                        <Icon className="size-5" />
                      </span>
                      <span
                        aria-hidden
                        className={`font-display text-sm font-bold tracking-wider ${numeralClass}`}
                      >
                        {String(index + 1).padStart(2, "0")}
                      </span>
                    </div>
                    <div className="relative">
                      <h3 className="text-title-3 font-semibold text-foreground">
                        <span className="sr-only">{index + 1}. </span>
                        {t(`steps.${key}.title`)}
                      </h3>
                      <p className="mt-2 text-sm leading-relaxed text-foreground">
                        {t(`steps.${key}.body`)}
                      </p>
                    </div>
                  </li>
                </Card>
              ),
            )}
          </ol>
        </div>
      </section>

      <div className="mx-auto grid w-full max-w-page gap-6 px-gutter pb-section md:grid-cols-2">
        <section
          id={homeSections.students}
          tabIndex={-1}
          aria-labelledby="students-title"
          className={`${sectionClassName} relative overflow-hidden rounded-3xl border border-sage-border bg-sage-soft p-7 shadow-sm sm:p-9`}
        >
          <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1.5 bg-sage" />
          <ArchWatermark tone="sage" className="absolute -right-4 -bottom-4 size-36 opacity-15" />
          <span
            aria-hidden
            className="relative grid size-12 place-items-center rounded-2xl bg-card text-sage-soft-foreground shadow-xs ring-1 ring-sage-border"
          >
            <ShieldCheck className="size-6" />
          </span>
          <h2 id="students-title" className="relative mt-5 text-title-2 font-bold tracking-tight">
            {t("students.title")}
          </h2>
          <p className="relative mt-3 text-base leading-relaxed text-foreground">
            {t("students.body")}
          </p>
        </section>
        <section
          id={homeSections.owners}
          tabIndex={-1}
          aria-labelledby="owners-title"
          className={`${sectionClassName} relative overflow-hidden rounded-3xl border border-coral-border bg-coral-soft p-7 shadow-sm sm:p-9`}
        >
          <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1.5 bg-coral" />
          <ArchWatermark tone="coral" className="absolute -right-4 -bottom-4 size-36 opacity-15" />
          <span
            aria-hidden
            className="relative grid size-12 place-items-center rounded-2xl bg-card text-coral-soft-foreground shadow-xs ring-1 ring-coral-border"
          >
            <KeyRound className="size-6" />
          </span>
          <h2 id="owners-title" className="relative mt-5 text-title-2 font-bold tracking-tight">
            {t("owners.title")}
          </h2>
          <p className="relative mt-3 text-base leading-relaxed text-foreground">
            {t("owners.body")}
          </p>
        </section>
      </div>

      <Suspense fallback={null}>
        <PopularPlaces />
      </Suspense>

      {/* Streams in after the page, so a slow or absent API never holds it up. */}
      <div className="mx-auto w-full max-w-page px-gutter pb-12">
        <Suspense fallback={<ApiStatusPending />}>
          <ApiStatus />
        </Suspense>
      </div>
    </>
  );
}
