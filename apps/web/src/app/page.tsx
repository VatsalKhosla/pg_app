import { CalendarCheck, KeyRound, MapPinned, ShieldCheck } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { homeSections } from "@/components/layout/navigation";
import { JsonLd } from "@/components/seo/json-ld";
import { buttonVariants } from "@/components/ui/button";
import { brand } from "@/config/brand";
import { publicEnv } from "@/config/env";
import { getSearchPlaces, type SearchPlace } from "@/lib/api/public";
import { organizationJsonLd } from "@/lib/seo/json-ld";
import { ApiStatus, ApiStatusPending } from "@/components/system/api-status";

const steps = [
  { key: "find", Icon: MapPinned },
  { key: "visit", Icon: CalendarCheck },
  { key: "reserve", Icon: ShieldCheck },
  { key: "moveIn", Icon: KeyRound },
] as const;

// Sections that the navigation links to: focusable, so a followed link can move focus here, and
// offset so the sticky header doesn't cover their headings.
const sectionClassName = "scroll-mt-20 outline-none";
// Places linked from the home page, of each kind: the ones with the most PGs.
const PLACES_SHOWN = 8;

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
    <section aria-labelledby="places-title" className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-6">
      <h2 id="places-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">
        {t("title")}
      </h2>
      <div className="mt-6 grid gap-8 md:grid-cols-2">
        {groups.map((group) => (
          <div key={group.title}>
            <h3 className="font-semibold">{group.title}</h3>
            <ul className="mt-3 flex flex-wrap gap-2">
              {group.items.map((place) => (
                <li key={place.slug}>
                  <Link
                    href={group.path(place.slug) as Route}
                    className="inline-flex min-h-11 items-center rounded-full border px-4 text-sm outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    {t("place", { name: place.name, count: place.listings })}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
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
      <section className="border-b bg-gradient-to-b from-accent/60 to-background">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
          <p className="inline-flex rounded-full border bg-background px-3 py-1 text-sm font-medium text-primary">
            {t("status")}
          </p>
          <h1 className="mt-6 max-w-3xl text-4xl font-bold tracking-tight text-balance sm:text-5xl">
            {tBrand("tagline")}
          </h1>
          <p className="mt-6 max-w-2xl text-lg text-pretty text-muted-foreground">{t("intro")}</p>
          <Link href="/search" className={buttonVariants({ size: "lg", className: "mt-8" })}>
            <MapPinned aria-hidden="true" />
            {t("findCta")}
          </Link>
        </div>
      </section>

      <section
        id={homeSections.howItWorks}
        tabIndex={-1}
        aria-labelledby="how-it-works-title"
        className={sectionClassName}
      >
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 id="how-it-works-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">
            {t("steps.title")}
          </h2>
          <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map(({ key, Icon }, index) => (
              <li key={key} className="rounded-xl border bg-card p-5 text-card-foreground">
                <div className="flex items-center gap-3">
                  <span
                    aria-hidden
                    className="grid size-10 place-items-center rounded-lg bg-primary/10 text-primary"
                  >
                    <Icon className="size-5" />
                  </span>
                  <h3 className="font-semibold">
                    <span className="sr-only">{index + 1}. </span>
                    {t(`steps.${key}.title`)}
                  </h3>
                </div>
                <p className="mt-3 text-sm text-muted-foreground">{t(`steps.${key}.body`)}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <div className="mx-auto grid w-full max-w-6xl gap-4 px-4 pb-16 sm:px-6 md:grid-cols-2">
        <section
          id={homeSections.students}
          tabIndex={-1}
          aria-labelledby="students-title"
          className={`${sectionClassName} rounded-xl border p-6`}
        >
          <h2 id="students-title" className="text-xl font-semibold tracking-tight">
            {t("students.title")}
          </h2>
          <p className="mt-3 text-muted-foreground">{t("students.body")}</p>
        </section>
        <section
          id={homeSections.owners}
          tabIndex={-1}
          aria-labelledby="owners-title"
          className={`${sectionClassName} rounded-xl border p-6`}
        >
          <h2 id="owners-title" className="text-xl font-semibold tracking-tight">
            {t("owners.title")}
          </h2>
          <p className="mt-3 text-muted-foreground">{t("owners.body")}</p>
        </section>
      </div>

      <Suspense fallback={null}>
        <PopularPlaces />
      </Suspense>

      {/* Streams in after the page, so a slow or absent API never holds it up. */}
      <div className="mx-auto w-full max-w-6xl px-4 pb-10 sm:px-6">
        <Suspense fallback={<ApiStatusPending />}>
          <ApiStatus />
        </Suspense>
      </div>
    </>
  );
}
