import type { Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { DuskScene } from "@/components/home/dusk-scene";
import { HeroParallax } from "@/components/home/hero-parallax";
import { type Choice, HeroSearch, type HeroSearchText } from "@/components/home/hero-search";
import { BudgetExplorerNear } from "@/components/home/islands";
import { StaySimulator } from "@/components/home/stay-simulator";
import { homeSections } from "@/components/layout/navigation";
import { JsonLd } from "@/components/seo/json-ld";
import { ApiStatus, ApiStatusPending } from "@/components/system/api-status";
import { buttonVariants } from "@/components/ui/button";
import { brand } from "@/config/brand";
import { publicEnv } from "@/config/env";
import { getPolicies, getSearchPlaces, type SearchPlace } from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { organizationJsonLd } from "@/lib/seo/json-ld";
import { trustPages } from "@/lib/trust/pages";

// Sections that the navigation links to: focusable, so a followed link can move focus here, and
// offset so the floating header doesn't cover their headings.
const sectionClassName = "scroll-mt-28 outline-none focus-visible:ring-2 focus-visible:ring-ring";
// Places linked from the home page, of each kind: the ones with the most PGs.
const PLACES_SHOWN = 8;
const BUDGETS_PAISE = [800_000, 1_000_000, 1_200_000, 1_500_000, 2_000_000] as const;
const MONTHS_SHOWN = 12;

async function placesOrNone(): Promise<SearchPlace[]> {
  try {
    return (await getSearchPlaces()).items;
  } catch {
    return [];
  }
}

async function policiesOrNull() {
  try {
    return await getPolicies();
  } catch {
    return null;
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

/** The promises, as figures from the live policy. Without the API there's nothing to state. */
async function PolicyFacts() {
  const policies = await policiesOrNull();
  if (policies === null) return null;
  const t = await getTranslations("Home.facts");
  const { tokenPaise, freeCancelDays, checkWindowHours } = policies.booking;
  const facts = [
    { value: formatINR(tokenPaise), label: t("token") },
    { value: t("days", { days: freeCancelDays }), label: t("cancel") },
    { value: t("hours", { hours: checkWindowHours }), label: t("check") },
    { value: formatINR(0), label: t("fee") },
  ];
  return (
    <section aria-labelledby="facts-title" className="mx-auto w-full max-w-page px-gutter">
      <h2 id="facts-title" className="sr-only">
        {t("title")}
      </h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-8 lg:grid-cols-4 lg:gap-x-10">
        {facts.map((fact) => (
          <div key={fact.label} className="flex flex-col-reverse justify-end gap-1.5">
            <dt className="max-w-[24ch] text-sm leading-snug text-muted-foreground">
              {fact.label}
            </dt>
            <dd className="text-title-1 font-semibold tabular-nums">{fact.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** One line of stops: each is a campus or locality with PGs, like a station on the Metro. */
function MetroLine({
  title,
  lineClass,
  stops,
}: {
  title: string;
  lineClass: string;
  stops: readonly { key: string; href: Route; name: string; detail: string }[];
}) {
  return (
    <div className="min-w-0">
      <h3 className="px-gutter font-sans text-base font-semibold lg:px-0">{title}</h3>
      <ul
        className="mt-4 flex snap-x scroll-px-gutter gap-0 overflow-x-auto px-gutter pb-3 [scrollbar-width:none] lg:px-0"
        style={{ "--line": lineClass }}
      >
        {stops.map((stop) => (
          <li key={stop.key} className="relative w-44 shrink-0 snap-start pt-1 sm:w-52">
            <span
              aria-hidden="true"
              className="absolute top-[0.8rem] left-0 h-1.5 w-full bg-(--line) group-last:w-0"
            />
            <Link
              href={stop.href}
              className="group relative block rounded-xl pr-4 pb-1 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <span
                aria-hidden="true"
                className="block size-5 rounded-full border-[5px] border-(--line) bg-background transition-colors duration-(--duration-fast) group-hover:bg-(--line) motion-reduce:transition-none"
              />
              <span className="mt-3 block font-medium leading-snug group-hover:underline group-hover:underline-offset-4">
                {stop.name}
              </span>
              <span className="mt-0.5 block text-sm text-muted-foreground">{stop.detail}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Links to the landing pages of the campuses and localities with the most PGs (step 3.6), for
 * people and search engines alike, drawn as two Metro lines. Without the API there's nothing to
 * link to, and the home page stands without it.
 */
async function PopularPlaces() {
  const places = await placesOrNone();
  if (places.length === 0) return null;
  const t = await getTranslations("Home.places");
  const stops = (kind: SearchPlace["kind"], base: string) =>
    places
      .filter((place) => place.kind === kind)
      .slice(0, PLACES_SHOWN)
      .map((place) => ({
        key: place.slug,
        href: `${base}/${place.slug}` as Route,
        name: place.name,
        detail: t("stop", { count: place.listings, rent: formatINR(place.minRentPaise) }),
      }));
  const lines = [
    { title: t("campuses"), lineClass: "var(--sun)", stops: stops("campus", "/pg-near") },
    { title: t("localities"), lineClass: "var(--dusk)", stops: stops("locality", "/pg-in") },
  ].filter((line) => line.stops.length > 0);
  return (
    <section
      aria-labelledby="places-title"
      className="mx-auto w-full max-w-page pt-section lg:px-gutter"
    >
      <h2 id="places-title" className="px-gutter text-title-1 font-medium lg:px-0">
        {t("title")}
      </h2>
      <div className="mt-8 grid gap-8">
        {lines.map((line) => (
          <MetroLine key={line.title} {...line} />
        ))}
      </div>
    </section>
  );
}

// Room held for the explorer, so the page doesn't move when it arrives (links to the sections
// below it land where they should).
const BUDGET_SPACE = "min-h-[39rem] lg:min-h-[27rem]";

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

const STEP_KEYS = ["find", "visit", "reserve", "moveIn"] as const;

/** The four steps in plain text: what the simulator starts from, and all there is without script. */
async function StepsList() {
  const t = await getTranslations("Home.steps");
  return (
    <ol className="grid max-w-3xl gap-6 sm:grid-cols-2">
      {STEP_KEYS.map((key) => (
        <li key={key}>
          <h3 className="text-title-3 font-medium">{t(`${key}.title`)}</h3>
          <p className="mt-1.5 leading-relaxed text-muted-foreground">{t(`${key}.body`)}</p>
        </li>
      ))}
    </ol>
  );
}

/** The simulator, with every word and figure read from the live policy here on the server. */
async function HomeSimulator() {
  const policies = await policiesOrNull();
  if (policies === null) return <StepsList />;
  const [t, tSim, tToken, tBookings] = await Promise.all([
    getTranslations("Home.steps"),
    getTranslations("Home.sim"),
    getTranslations("TokenProtection"),
    getTranslations("Bookings.next"),
  ]);
  const { tokenPaise, freeCancelDays, checkWindowHours, confirmDeadlineHours } = policies.booking;
  const stages = [
    { key: "find", title: t("find.title"), body: t("find.body"), place: 0 },
    { key: "visit", title: t("visit.title"), body: t("visit.body"), place: 0 },
    { key: "reserve", title: t("reserve.title"), body: t("reserve.body"), place: 1 },
    {
      key: "confirm",
      title: tSim("confirm"),
      body: tToken("confirm", { confirmHours: confirmDeadlineHours }),
      place: 1,
    },
    { key: "moveIn", title: t("moveIn.title"), body: t("moveIn.body"), place: 1 },
    {
      key: "check",
      title: tSim("check"),
      body: tToken("held", { checkHours: checkWindowHours }),
      place: 1,
    },
    { key: "settled", title: tSim("settled"), body: tBookings("active"), place: 2 },
  ] as const;
  const branches = [
    {
      key: "cancel",
      stages: ["reserve", "confirm"],
      label: tSim("cancelLabel"),
      body: tToken("cancel", { freeCancelDays }),
    },
    {
      key: "ownerNo",
      stages: ["confirm"],
      label: tSim("ownerNoLabel"),
      body: tBookings("rejected"),
    },
    {
      key: "notAsShown",
      stages: ["check"],
      label: tSim("notAsShownLabel"),
      body: tToken("notAsShown", { checkHours: checkWindowHours }),
    },
  ];
  return (
    <StaySimulator
      token={formatINR(tokenPaise)}
      stages={stages}
      branches={branches}
      text={{
        scrub: tSim("scrub"),
        step: tSim.raw("step") as string,
        places: [tSim("you"), tSim("held"), tSim("rent")],
        back: tSim("back"),
        play: tSim("play"),
        pause: tSim("pause"),
        happens: tSim("happens"),
        onTrack: tSim("onTrack"),
      }}
    />
  );
}

export default async function HomePage() {
  const [t, tBudget, tTrust] = await Promise.all([
    getTranslations("Home"),
    getTranslations("Home.budget"),
    getTranslations("Trust.pages"),
  ]);
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
        <Suspense fallback={<div className="min-h-32" />}>
          <PolicyFacts />
        </Suspense>
      </div>

      <Suspense fallback={null}>
        <PopularPlaces />
      </Suspense>

      <section
        id={homeSections.howItWorks}
        tabIndex={-1}
        aria-labelledby="how-it-works-title"
        className={sectionClassName}
      >
        <div className="mx-auto max-w-page px-gutter py-section">
          <h2 id="how-it-works-title" className="text-display font-medium">
            {t("steps.title")}
          </h2>
          <p className="mt-3 max-w-prose text-lg text-muted-foreground">{t("steps.lead")}</p>
          <div className="mt-10">
            <Suspense fallback={<StepsList />}>
              <HomeSimulator />
            </Suspense>
          </div>
        </div>
      </section>

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
            <Suspense fallback={<div className={BUDGET_SPACE} />}>
              <BudgetBand />
            </Suspense>
          </div>
        </div>
      </section>

      <Suspense fallback={null}>
        <div className="mx-auto grid w-full max-w-page gap-12 px-gutter py-section md:grid-cols-2 md:gap-16">
          <section
            id={homeSections.students}
            tabIndex={-1}
            aria-labelledby="students-title"
            className={sectionClassName}
          >
            <h2 id="students-title" className="text-title-1 font-medium">
              {t("students.title")}
            </h2>
            <p className="mt-3 max-w-prose text-lg leading-relaxed text-muted-foreground">
              {t("students.body")}
            </p>
            <Link
              href={trustPages.tokenProtection}
              className="mt-4 inline-flex min-h-11 items-center font-semibold text-primary underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {tTrust("tokenProtection")}
            </Link>
          </section>
          <section
            id={homeSections.owners}
            tabIndex={-1}
            aria-labelledby="owners-title"
            className={sectionClassName}
          >
            <h2 id="owners-title" className="text-title-1 font-medium">
              {t("owners.title")}
            </h2>
            <p className="mt-3 max-w-prose text-lg leading-relaxed text-muted-foreground">
              {t("owners.body")}
            </p>
            <Link
              href={trustPages.pricing}
              className="mt-4 inline-flex min-h-11 items-center font-semibold text-primary underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {tTrust("pricing")}
            </Link>
          </section>
        </div>
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
