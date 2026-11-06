import { CalendarCheck, KeyRound, MapPinned, ShieldCheck } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

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
  { key: "find", Icon: MapPinned },
  { key: "visit", Icon: CalendarCheck },
  { key: "reserve", Icon: ShieldCheck },
  { key: "moveIn", Icon: KeyRound },
] as const;

// Sections that the navigation links to: focusable, so a followed link can move focus here, and
// offset so the sticky header doesn't cover their headings.
const sectionClassName = "scroll-mt-24 outline-none focus-visible:ring-2 focus-visible:ring-ring";
// Places linked from the home page, of each kind: the ones with the most PGs.
const PLACES_SHOWN = 8;

const placeChipClasses =
  "inline-flex min-h-11 items-center rounded-full border border-input/70 bg-surface px-4 py-2 text-sm font-medium text-foreground shadow-2xs transition-[background-color,border-color,color,transform] duration-(--duration-fast) ease-standard outline-none hover:-translate-y-0.5 hover:border-primary hover:bg-primary-soft hover:text-primary-soft-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none motion-reduce:hover:translate-y-0";

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
      items: places.filter((place) => place.kind === "campus").slice(0, PLACES_SHOWN),
      path: (slug: string) => `/pg-near/${slug}`,
    },
    {
      title: t("localities"),
      items: places.filter((place) => place.kind === "locality").slice(0, PLACES_SHOWN),
      path: (slug: string) => `/pg-in/${slug}`,
    },
  ].filter((group) => group.items.length > 0);
  return (
    <section
      aria-labelledby="places-title"
      className="mx-auto w-full max-w-page px-gutter pb-section"
    >
      <h2 id="places-title" className="text-title-1 font-bold tracking-tight">
        {t("title")}
      </h2>
      <div className="mt-8 grid gap-6 md:grid-cols-2">
        {groups.map((group) => (
          <Card key={group.title} variant="flat" className="rounded-2xl p-6 sm:p-7">
            <h3 className="text-title-3 font-semibold text-foreground">{group.title}</h3>
            <ul className="mt-4 flex flex-wrap gap-2.5">
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
      <section className="relative overflow-hidden border-b bg-surface">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(48rem_28rem_at_50%_0%,var(--primary-soft),transparent)]"
        />
        <div className="relative mx-auto max-w-page px-gutter py-16 sm:py-24 lg:py-28">
          <Badge variant="brand" className="gap-2 px-3.5 py-1 text-xs font-semibold shadow-2xs">
            <span aria-hidden className="size-1.5 rounded-full bg-primary" />
            {t("status")}
          </Badge>
          <h1 className="mt-6 max-w-3xl text-display font-bold tracking-tight text-foreground">
            {tBrand("tagline")}
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
            {t("intro")}
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              href="/search"
              className={buttonVariants({ size: "lg", shape: "pill", className: "shadow-md" })}
            >
              <MapPinned aria-hidden="true" />
              {t("findCta")}
            </Link>
          </div>
        </div>
      </section>

      <section
        id={homeSections.howItWorks}
        tabIndex={-1}
        aria-labelledby="how-it-works-title"
        className={sectionClassName}
      >
        <div className="mx-auto max-w-page px-gutter py-section">
          <h2 id="how-it-works-title" className="text-title-1 font-bold tracking-tight">
            {t("steps.title")}
          </h2>
          <ol className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map(({ key, Icon }, index) => (
              <Card
                key={key}
                asChild
                variant="raised"
                className="justify-between gap-6 rounded-2xl p-6"
              >
                <li>
                  <div className="flex items-center justify-between gap-3">
                    <span
                      aria-hidden
                      className="grid size-12 place-items-center rounded-xl bg-primary-soft text-primary-soft-foreground"
                    >
                      <Icon className="size-5" />
                    </span>
                    <span
                      aria-hidden
                      className="font-display text-xs font-bold tracking-wider text-muted-foreground"
                    >
                      {String(index + 1).padStart(2, "0")}
                    </span>
                  </div>
                  <div>
                    <h3 className="text-title-3 font-semibold text-foreground">
                      <span className="sr-only">{index + 1}. </span>
                      {t(`steps.${key}.title`)}
                    </h3>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {t(`steps.${key}.body`)}
                    </p>
                  </div>
                </li>
              </Card>
            ))}
          </ol>
        </div>
      </section>

      <div className="mx-auto grid w-full max-w-page gap-6 px-gutter pb-section md:grid-cols-2">
        <section
          id={homeSections.students}
          tabIndex={-1}
          aria-labelledby="students-title"
          className={`${sectionClassName} rounded-3xl border bg-surface p-7 shadow-xs sm:p-9`}
        >
          <span
            aria-hidden
            className="grid size-12 place-items-center rounded-2xl bg-primary-soft text-primary-soft-foreground"
          >
            <ShieldCheck className="size-6" />
          </span>
          <h2 id="students-title" className="mt-5 text-title-2 font-bold tracking-tight">
            {t("students.title")}
          </h2>
          <p className="mt-3 text-base leading-relaxed text-muted-foreground">
            {t("students.body")}
          </p>
        </section>
        <section
          id={homeSections.owners}
          tabIndex={-1}
          aria-labelledby="owners-title"
          className={`${sectionClassName} rounded-3xl border bg-card p-7 shadow-sm sm:p-9`}
        >
          <span
            aria-hidden
            className="grid size-12 place-items-center rounded-2xl bg-secondary text-secondary-foreground"
          >
            <KeyRound className="size-6" />
          </span>
          <h2 id="owners-title" className="mt-5 text-title-2 font-bold tracking-tight">
            {t("owners.title")}
          </h2>
          <p className="mt-3 text-base leading-relaxed text-muted-foreground">{t("owners.body")}</p>
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
