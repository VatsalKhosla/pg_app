import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { LandingPage } from "@/components/landing/landing-page";
import { brand } from "@/config/brand";
import {
  getSearchPage,
  getSearchPlaces,
  getSearchReference,
  type SearchPlaces,
} from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { metresBetween } from "@/lib/search/area";

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/u;
// As many as search's first page: the map has the rest.
const LIST_SIZE = 12;

async function localityFor(slug: string) {
  if (!SLUG.test(slug) || slug.length > 64) notFound();
  const { localities, campuses } = await getSearchReference();
  const locality = localities.find((each) => each.slug === slug);
  if (locality === undefined) notFound();
  return { locality, campuses };
}

function placeOf(places: SearchPlaces, slug: string) {
  return places.items.find((item) => item.kind === "locality" && item.slug === slug);
}

export async function generateMetadata({
  params,
}: PageProps<"/pg-in/[locality]">): Promise<Metadata> {
  const { locality: slug } = await params;
  const [{ locality }, places] = await Promise.all([localityFor(slug), getSearchPlaces()]);
  const place = placeOf(places, slug);
  const t = await getTranslations("Landing");
  const title = t("in.title", { locality: locality.name });
  const description =
    place === undefined
      ? t("in.noneDescription", { locality: locality.name })
      : t("in.description", {
          count: place.listings,
          locality: locality.name,
          min: formatINR(place.minRentPaise),
        });
  const path = `/pg-in/${slug}`;
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { title, description, url: path, type: "website" },
    // A page with no PG on it yet isn't worth a search engine's while.
    robots: place === undefined ? { index: false, follow: true } : undefined,
  };
}

/**
 * PGs in a locality (ARCHITECTURE §10.6; step 3.6, ADR 0032): the verified live ones there,
 * as search recommends them, with their numbers in words and the campuses within reach.
 */
export default async function InLocalityPage({ params }: PageProps<"/pg-in/[locality]">) {
  const { locality: slug } = await params;
  const [{ locality, campuses }, places] = await Promise.all([
    localityFor(slug),
    getSearchPlaces(),
  ]);
  const place = placeOf(places, slug);
  const found =
    place === undefined ? null : await getSearchPage({ locality: slug, limit: LIST_SIZE });
  const cards = found !== null && "page" in found ? found.page.items : [];
  const t = await getTranslations("Landing");
  const format = await getFormatter();
  const month = format.dateTime(new Date(`${places.month}T00:00:00Z`), {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  // The campuses with PGs whose reach takes in the locality's centre, nearest first.
  const withPgs = new Map(
    places.items.filter((item) => item.kind === "campus").map((item) => [item.slug, item]),
  );
  const nearby = campuses
    .map((campus) => ({ campus, metres: metresBetween(campus.location, locality.center) }))
    .filter(({ campus, metres }) => metres <= places.radiusM && withPgs.has(campus.slug))
    .sort((a, b) => a.metres - b.metres)
    .map(({ campus }) => ({
      href: `/pg-near/${campus.slug}`,
      label: t("place", { name: campus.name, count: withPgs.get(campus.slug)?.listings ?? 0 }),
    }));
  const prices =
    place === undefined
      ? null
      : { min: formatINR(place.minRentPaise), max: formatINR(place.maxRentPaise) };

  return (
    <LandingPage
      path={`/pg-in/${slug}`}
      text={{
        title: t("in.title", { locality: locality.name }),
        intro:
          place === undefined || prices === null
            ? null
            : t("in.intro", { count: place.listings, locality: locality.name, month, ...prices }),
        none: t("in.none", { locality: locality.name }),
        noneHint: t("noneHint"),
        map: t("map"),
        mapAll:
          place !== undefined && place.listings > cards.length
            ? t("mapAll", { count: place.listings })
            : null,
        list: t("list"),
        nearby: t("campuses"),
        breadcrumb: t("breadcrumb"),
        home: t("home"),
        search: t("search"),
        faq: t("faq.title"),
      }}
      cards={cards}
      mapHref={`/search?locality=${slug}`}
      nearby={nearby}
      faqs={
        place === undefined || prices === null
          ? []
          : [
              {
                question: t("in.faqCount", { locality: locality.name }),
                answer: t("faq.countAnswer", { count: place.listings }),
              },
              {
                question: t("in.faqPrice", { locality: locality.name }),
                answer: t("faq.priceAnswer", { month, ...prices }),
              },
              {
                question: t("faq.feeQuestion", { brand: brand.name }),
                answer: t("faq.feeAnswer"),
              },
              { question: t("faq.checkQuestion"), answer: t("faq.checkAnswer") },
            ]
      }
    />
  );
}
