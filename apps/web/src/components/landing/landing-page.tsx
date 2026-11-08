import { MapPinned } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";

import { ArchWatermark } from "@/components/brand/editorial-art";
import { PgCard } from "@/components/search/pg-card";
import { JsonLd } from "@/components/seo/json-ld";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { publicEnv } from "@/config/env";
import type { SearchCard } from "@/lib/search/client";
import { breadcrumbJsonLd, faqJsonLd, itemListJsonLd } from "@/lib/seo/json-ld";

export interface LandingText {
  title: string;
  /** How many PGs and what they cost; null when there are none yet. */
  intro: string | null;
  none: string;
  noneHint: string;
  map: string;
  /** "See all 30 on the map", when the page lists only some of them. */
  mapAll: string | null;
  list: string;
  nearby: string;
  breadcrumb: string;
  home: string;
  search: string;
  faq: string;
}

const nearbyChipClasses =
  "inline-flex min-h-11 items-center rounded-full border border-marigold-border bg-marigold-soft px-4 py-2 text-sm font-medium text-marigold-soft-foreground shadow-2xs transition-[background-color,border-color,color,transform] duration-(--duration-fast) ease-standard outline-none hover:-translate-y-0.5 hover:border-ember hover:bg-ember-soft hover:text-ember-soft-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none motion-reduce:hover:translate-y-0";

const faqVariants = ["ink", "marigold", "dusk", "neem"] as const;

/**
 * A landing page for a campus or a locality (step 3.6, ADR 0032): the PGs there as search finds
 * them, rendered on the server with no script of their own, a way onto the map, the places
 * nearby, and answers drawn from the same live numbers. Structured data says the same for
 * search engines: the list, the breadcrumbs and the questions.
 */
export function LandingPage({
  path,
  text,
  cards,
  mapHref,
  nearby,
  faqs,
}: {
  path: string;
  text: LandingText;
  cards: readonly SearchCard[];
  mapHref: string;
  nearby: readonly { href: string; label: string }[];
  faqs: readonly { question: string; answer: string }[];
}) {
  const absolute = (to: string) => new URL(to, publicEnv.siteUrl).toString();
  const crumbs = [
    { name: text.home, path: "/" },
    { name: text.search, path: "/search" },
    { name: text.title, path },
  ];
  return (
    <div>
      <JsonLd
        data={[
          itemListJsonLd(text.title, cards, absolute),
          breadcrumbJsonLd(
            crumbs.map((crumb) => ({ name: crumb.name, url: absolute(crumb.path) })),
          ),
          ...(faqs.length === 0 ? [] : [faqJsonLd(faqs)]),
        ]}
      />
      <header className="relative overflow-hidden border-b border-marigold-border/70 bg-surface-warm">
        <ArchWatermark tone="ember" className="absolute -right-6 -bottom-6 size-48 opacity-15" />
        <div className="relative mx-auto max-w-page space-y-4 px-gutter py-10 sm:py-14">
          <nav aria-label={text.breadcrumb}>
            <ol className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
              {crumbs.slice(0, -1).map((crumb) => (
                <li key={crumb.path} className="flex items-center gap-1.5">
                  <Link
                    href={crumb.path as Route}
                    className="inline-flex min-h-8 items-center rounded-md px-1 underline-offset-4 transition-colors outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
                  >
                    {crumb.name}
                  </Link>
                  <span aria-hidden="true">/</span>
                </li>
              ))}
              <li aria-current="page" className="font-medium text-foreground">
                {text.title}
              </li>
            </ol>
          </nav>
          <div aria-hidden="true" className="flex items-center gap-1.5">
            <span className="h-1.5 w-8 rounded-full bg-ember" />
            <span className="h-1.5 w-5 rounded-full bg-marigold" />
            <span className="h-1.5 w-4 rounded-full bg-primary" />
          </div>
          <h1 className="max-w-3xl text-title-1 font-bold tracking-tight text-foreground">
            {text.title}
          </h1>
          <p className="max-w-2xl text-lg leading-relaxed text-muted-foreground">
            {text.intro ?? text.none}
          </p>
          {text.intro === null ? (
            <p className="max-w-2xl text-muted-foreground">{text.noneHint}</p>
          ) : null}
          <div className="pt-2">
            <Link
              href={mapHref as Route}
              className={buttonVariants({ size: "lg", shape: "pill", className: "shadow-md" })}
            >
              <MapPinned aria-hidden="true" />
              {text.map}
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-page space-y-14 px-gutter py-10 sm:py-14">
        {cards.length === 0 ? null : (
          <section aria-labelledby="landing-list" className="space-y-6">
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="h-6 w-1.5 rounded-full bg-primary" />
              <h2 id="landing-list" className="text-title-2 font-bold tracking-tight">
                {text.list}
              </h2>
            </div>
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {cards.map((card, index) => (
                <li key={card.id}>
                  <PgCard card={card} first={index === 0} />
                </li>
              ))}
            </ul>
            {text.mapAll === null ? null : (
              <div>
                <Link
                  href={mapHref as Route}
                  className={buttonVariants({ variant: "outline", size: "lg", shape: "pill" })}
                >
                  {text.mapAll}
                </Link>
              </div>
            )}
          </section>
        )}

        {nearby.length === 0 ? null : (
          <section aria-labelledby="landing-nearby" className="space-y-4">
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="h-6 w-1.5 rounded-full bg-marigold" />
              <h2 id="landing-nearby" className="text-title-2 font-bold tracking-tight">
                {text.nearby}
              </h2>
            </div>
            <ul className="flex flex-wrap gap-2.5">
              {nearby.map((place) => (
                <li key={place.href}>
                  <Link href={place.href as Route} className={nearbyChipClasses}>
                    {place.label}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {faqs.length === 0 ? null : (
          <section aria-labelledby="landing-faq" className="space-y-6">
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="h-6 w-1.5 rounded-full bg-dusk" />
              <h2 id="landing-faq" className="text-title-2 font-bold tracking-tight">
                {text.faq}
              </h2>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {faqs.map((faq, index) => (
                <Card
                  key={faq.question}
                  variant={faqVariants[index % faqVariants.length]}
                  className="rounded-2xl p-6"
                >
                  <h3 className="text-base font-semibold text-foreground">{faq.question}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-foreground">{faq.answer}</p>
                </Card>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
