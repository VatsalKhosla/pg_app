import type { Route } from "next";
import Link from "next/link";
import { MapPinned } from "lucide-react";

import { JsonLd } from "@/components/seo/json-ld";
import { PgCard } from "@/components/search/pg-card";
import { buttonVariants } from "@/components/ui/button";
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
    <div className="mx-auto w-full max-w-3xl space-y-10 px-4 py-8 sm:px-6 sm:py-12">
      <JsonLd
        data={[
          itemListJsonLd(text.title, cards, absolute),
          breadcrumbJsonLd(
            crumbs.map((crumb) => ({ name: crumb.name, url: absolute(crumb.path) })),
          ),
          ...(faqs.length === 0 ? [] : [faqJsonLd(faqs)]),
        ]}
      />
      <header className="space-y-4">
        <nav aria-label={text.breadcrumb}>
          <ol className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
            {crumbs.slice(0, -1).map((crumb) => (
              <li key={crumb.path} className="flex items-center gap-1">
                <Link
                  href={crumb.path as Route}
                  className="rounded underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {crumb.name}
                </Link>
                <span aria-hidden="true">/</span>
              </li>
            ))}
            <li aria-current="page">{text.title}</li>
          </ol>
        </nav>
        <h1 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">{text.title}</h1>
        <p className="text-lg text-pretty text-muted-foreground">{text.intro ?? text.none}</p>
        {text.intro === null ? <p className="text-muted-foreground">{text.noneHint}</p> : null}
        <Link href={mapHref as Route} className={buttonVariants({ size: "lg" })}>
          <MapPinned aria-hidden="true" />
          {text.map}
        </Link>
      </header>

      {cards.length === 0 ? null : (
        <section aria-labelledby="landing-list" className="space-y-4">
          <h2 id="landing-list" className="text-xl font-semibold tracking-tight">
            {text.list}
          </h2>
          <ul className="space-y-3">
            {cards.map((card, index) => (
              <li key={card.id}>
                <PgCard card={card} first={index === 0} />
              </li>
            ))}
          </ul>
          {text.mapAll === null ? null : (
            <Link
              href={mapHref as Route}
              className={buttonVariants({ variant: "outline", className: "w-full" })}
            >
              {text.mapAll}
            </Link>
          )}
        </section>
      )}

      {nearby.length === 0 ? null : (
        <section aria-labelledby="landing-nearby" className="space-y-3">
          <h2 id="landing-nearby" className="text-xl font-semibold tracking-tight">
            {text.nearby}
          </h2>
          <ul className="flex flex-wrap gap-2">
            {nearby.map((place) => (
              <li key={place.href}>
                <Link
                  href={place.href as Route}
                  className="inline-flex min-h-11 items-center rounded-full border px-4 text-sm outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {place.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {faqs.length === 0 ? null : (
        <section aria-labelledby="landing-faq" className="space-y-4">
          <h2 id="landing-faq" className="text-xl font-semibold tracking-tight">
            {text.faq}
          </h2>
          <div className="space-y-5">
            {faqs.map((faq) => (
              <div key={faq.question} className="space-y-1">
                <h3 className="font-medium">{faq.question}</h3>
                <p className="text-muted-foreground">{faq.answer}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
