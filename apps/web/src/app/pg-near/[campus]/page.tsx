import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { LandingPage } from "@/components/landing/landing-page";
import { brand } from "@/config/brand";
import {
  type CampusDetail,
  getCampus,
  getSearchPage,
  getSearchPlaces,
  type SearchPlaces,
} from "@/lib/api/public";
import { formatINR } from "@/lib/money";

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/u;
// As many as search's first page: the map has the rest.
const LIST_SIZE = 12;

async function campusFor(slug: string): Promise<CampusDetail> {
  if (!SLUG.test(slug) || slug.length > 64) notFound();
  const campus = await getCampus(slug);
  if (campus === null) notFound();
  return campus;
}

function placeOf(places: SearchPlaces, slug: string) {
  return places.items.find((item) => item.kind === "campus" && item.slug === slug);
}

export async function generateMetadata({
  params,
}: PageProps<"/pg-near/[campus]">): Promise<Metadata> {
  const { campus: slug } = await params;
  const [campus, places] = await Promise.all([campusFor(slug), getSearchPlaces()]);
  const place = placeOf(places, slug);
  const t = await getTranslations("Landing");
  const title = t("near.title", { campus: campus.name });
  const description =
    place === undefined
      ? t("near.noneDescription", { campus: campus.name })
      : t("near.description", {
          count: place.listings,
          km: places.radiusM / 1_000,
          campus: campus.name,
          min: formatINR(place.minRentPaise),
        });
  const path = `/pg-near/${slug}`;
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
 * PGs near a campus (ARCHITECTURE §10.6; step 3.6, ADR 0032): the verified live ones within
 * search's radius, nearest first, with their numbers in words and the localities around it.
 */
export default async function NearCampusPage({ params }: PageProps<"/pg-near/[campus]">) {
  const { campus: slug } = await params;
  const [campus, places] = await Promise.all([campusFor(slug), getSearchPlaces()]);
  const place = placeOf(places, slug);
  const found =
    place === undefined
      ? null
      : await getSearchPage({ campus: slug, sort: "distance", limit: LIST_SIZE });
  const cards = found !== null && "page" in found ? found.page.items : [];
  const t = await getTranslations("Landing");
  const format = await getFormatter();
  const month = format.dateTime(new Date(`${places.month}T00:00:00Z`), {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  const km = places.radiusM / 1_000;
  const localities = new Map(
    places.items.filter((item) => item.kind === "locality").map((item) => [item.slug, item]),
  );
  const nearby = campus.localities.flatMap(({ locality }) => {
    const there = localities.get(locality.slug);
    return there === undefined
      ? []
      : [
          {
            href: `/pg-in/${locality.slug}`,
            label: t("place", { name: locality.name, count: there.listings }),
          },
        ];
  });
  const prices =
    place === undefined
      ? null
      : { min: formatINR(place.minRentPaise), max: formatINR(place.maxRentPaise) };

  return (
    <LandingPage
      path={`/pg-near/${slug}`}
      text={{
        title: t("near.title", { campus: campus.name }),
        intro:
          place === undefined || prices === null
            ? null
            : t("near.intro", { count: place.listings, km, campus: campus.name, month, ...prices }),
        none: t("near.none", { km, campus: campus.name }),
        noneHint: t("noneHint"),
        map: t("map"),
        mapAll:
          place !== undefined && place.listings > cards.length
            ? t("mapAll", { count: place.listings })
            : null,
        list: t("list"),
        nearby: t("localities"),
        breadcrumb: t("breadcrumb"),
        home: t("home"),
        search: t("search"),
        faq: t("faq.title"),
      }}
      cards={cards}
      mapHref={`/search?campus=${slug}`}
      nearby={nearby}
      faqs={
        place === undefined || prices === null
          ? []
          : [
              {
                question: t("near.faqCount", { campus: campus.name }),
                answer: t("faq.countAnswer", { count: place.listings }),
              },
              {
                question: t("near.faqPrice", { campus: campus.name }),
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
