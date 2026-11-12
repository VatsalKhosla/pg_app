import { ArrowRight, Building2, Route as RouteIcon, Users } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { DuskScene } from "@/components/home/dusk-scene";
import { HeroParallax } from "@/components/home/hero-parallax";
import { type Choice, HeroSearch, type HeroSearchText } from "@/components/home/hero-search";
import { BudgetExplorerNear } from "@/components/home/islands";
import { JsonLd } from "@/components/seo/json-ld";
import { MetroLines } from "@/components/story/metro-lines";
import { PolicyFacts } from "@/components/story/policy-facts";
import { ApiStatus, ApiStatusPending } from "@/components/system/api-status";
import { buttonVariants } from "@/components/ui/button-variants";
import { brand } from "@/config/brand";
import { publicEnv } from "@/config/env";
import { getSearchPlaces, type SearchPlace } from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { organizationJsonLd } from "@/lib/seo/json-ld";

const BUDGETS_PAISE = [800_000, 1_000_000, 1_200_000, 1_500_000, 2_000_000] as const;
const MONTHS_SHOWN = 12;
// Room held for the explorer, so the page doesn't move when it arrives.
const BUDGET_SPACE = "min-h-[39rem] lg:min-h-[27rem]";

async function placesOrNone(): Promise<SearchPlace[]> {
  try {
    return (await getSearchPlaces()).items;
  } catch {
    return [];
  }
}

/** The next twelve months, in India's calendar, for the search's move-in choice. */
function nextMonths(): Choice[] {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  const year = Number(parts.find((part) => part.type === "year")?.value);
  const month = Number(parts.find((part) => part.type === "month")?.value);
  const label = new Intl.DateTimeFormat("en-IN", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  return Array.from({ length: MONTHS_SHOWN }, (_, offset) => {
    const date = new Date(Date.UTC(year, month - 1 + offset, 1));
    const value = [
      String(date.getUTCFullYear()),
      String(date.getUTCMonth() + 1).padStart(2, "0"),
    ].join("-");
    return { value, label: label.format(date) };
  });
}

async function heroSearchText() {
  const t = await getTranslations("Home.search");
  const text: HeroSearchText = {
    label: t("label"),
    near: t("near"),
    anywhere: t("anywhere"),
    moveIn: t("moveIn"),
    anyMonth: t("anyMonth"),
    budget: t("budget"),
    anyBudget: t("anyBudget"),
    submit: t("submit"),
  };
  const budgets: Choice[] = BUDGETS_PAISE.map((paise) => ({
    value: String(paise),
    label: t("upTo", { amount: formatINR(paise) }),
  }));
  return { text, budgets, months: nextMonths() };
}

/** The search with the campuses filled in; it streams in, so a slow API never holds up the hero. */
async function HeroSearchWithCampuses() {
  const [common, places] = await Promise.all([heroSearchText(), placesOrNone()]);
  const campuses = places
    .filter((place) => place.kind === "campus")
    .map((place) => ({ value: place.slug, label: place.name }));
  return <HeroSearch {...common} campuses={campuses} />;
}

async function HeroSearchPending() {
  const common = await heroSearchText();
  return <HeroSearch {...common} campuses={[]} />;
}

/** The budget explorer where there are PGs to show; otherwise a plain way to the map. */
async function BudgetBand() {
  const [t, places] = await Promise.all([getTranslations("Home.budget"), placesOrNone()]);
  const fallback = (
    <div className="flex flex-wrap items-center gap-5">
      <p className="max-w-prose text-lg text-night-foreground">{t("fallback")}</p>
      <Link
        href="/search"
        className={buttonVariants({ variant: "sun", size: "lg", shape: "pill" })}
      >
        {t("fallbackCta")}
      </Link>
    </div>
  );
  if (places.length === 0) return fallback;
  return (
    <div className={BUDGET_SPACE}>
      <BudgetExplorerNear
        text={{
          budget: t("label"),
          one: t.raw("one") as string,
          other: t.raw("other") as string,
          none: t.raw("none") as string,
          more: t("more"),
          cta: t("cta"),
          monthly: t("monthly"),
          caption: t("caption"),
          mapLabel: t("mapLabel"),
        }}
      >
        {fallback}
      </BudgetExplorerNear>
    </div>
  );
}

const DOORS = [
  { key: "howItWorks", href: "/how-it-works", Icon: RouteIcon, tone: "from-primary" },
  { key: "students", href: "/students", Icon: Users, tone: "from-dusk" },
  { key: "owners", href: "/owners", Icon: Building2, tone: "from-ember" },
] as const;

/** Three ways in: how it works, and the pages for students and for owners. */
async function Doors() {
  const t = await getTranslations("Home.doors");
  return (
    <section
      aria-labelledby="doors-title"
      className="mx-auto w-full max-w-page px-gutter py-section"
    >
      <h2 id="doors-title" className="text-display font-medium">
        {t("title")}
      </h2>
      <ul className="mt-10 grid gap-5 md:grid-cols-3">
        {DOORS.map(({ key, href, Icon, tone }) => (
          <li key={key}>
            <Link
              href={href as Route}
              className="group relative flex h-full flex-col gap-4 overflow-hidden rounded-[1.75rem] border border-border/70 bg-card p-7 shadow-md outline-none transition-[transform,box-shadow] duration-(--duration-base) ease-standard hover:-translate-y-1 hover:shadow-xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none motion-reduce:hover:translate-y-0"
            >
              <span
                aria-hidden="true"
                className={`grid size-13 place-items-center rounded-2xl bg-linear-to-br ${tone} to-[color-mix(in_oklch,var(--sun)_70%,var(--ember))] text-white shadow-md`}
              >
                <Icon className="size-6" />
              </span>
              <h3 className="text-title-2 font-medium">{t(`${key}.title`)}</h3>
              <p className="flex-1 leading-relaxed text-muted-foreground">{t(`${key}.body`)}</p>
              <span className="inline-flex items-center gap-1.5 font-semibold text-primary">
                {t("open")}
                <ArrowRight
                  aria-hidden="true"
                  className="size-4 transition-transform duration-(--duration-base) group-hover:translate-x-1 motion-reduce:transition-none"
                />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default async function HomePage() {
  const [t, tBudget] = await Promise.all([getTranslations("Home"), getTranslations("Home.budget")]);
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

      <section className="relative -mt-[4.75rem]">
        <div className="scope-night relative isolate min-h-[max(40rem,min(92svh,58rem))] overflow-hidden rounded-b-[2rem] pt-[4.75rem] sm:rounded-b-[3.5rem]">
          {/* Its own boundary: React hydrates it after the page's first task, not during it. */}
          <Suspense fallback={null}>
            <DuskScene />
          </Suspense>
          <HeroParallax />
          <Suspense fallback={null}>
            <div className="relative mx-auto max-w-page px-gutter pt-[clamp(2.5rem,9svh,6.5rem)] pb-64">
              <h1 className="max-w-[13ch] text-hero font-medium">
                {t.rich("headline", {
                  accent: (chunks) => <span className="text-night-accent">{chunks}</span>,
                })}
              </h1>
              <p className="mt-6 max-w-[34rem] text-lg leading-relaxed text-night-foreground sm:text-xl">
                {t("intro")}
              </p>
              <p className="mt-5 inline-flex items-center gap-2 rounded-full bg-night/60 px-3.5 py-1.5 text-sm font-medium text-night-foreground">
                <span aria-hidden="true" className="size-2 rounded-full bg-night-accent" />
                {t("status")}
              </p>
            </div>
          </Suspense>
        </div>
        <div className="relative z-10 mx-auto -mt-16 max-w-4xl px-gutter sm:-mt-10">
          <Suspense fallback={<HeroSearchPending />}>
            <HeroSearchWithCampuses />
          </Suspense>
        </div>
      </section>

      <div className="pt-14 sm:pt-20">
        <Suspense fallback={null}>
          <PolicyFacts />
        </Suspense>
      </div>

      <Suspense fallback={null}>
        <MetroLines />
      </Suspense>

      <Suspense fallback={null}>
        <Doors />
      </Suspense>

      <section
        aria-labelledby="budget-title"
        className="scope-night rounded-[2rem] sm:rounded-[3.5rem]"
      >
        <div className="mx-auto max-w-page px-gutter py-section">
          <h2 id="budget-title" className="text-display font-medium">
            {tBudget("title")}
          </h2>
          <p className="mt-3 max-w-prose text-lg text-muted-foreground">{tBudget("lead")}</p>
          <div className="mt-10">
            <Suspense fallback={null}>
              <BudgetBand />
            </Suspense>
          </div>
        </div>
      </section>

      {/* Streams in after the page, so a slow or absent API never holds it up. */}
      <div className="mx-auto w-full max-w-page px-gutter py-12">
        <Suspense fallback={<ApiStatusPending />}>
          <ApiStatus />
        </Suspense>
      </div>
    </>
  );
}
