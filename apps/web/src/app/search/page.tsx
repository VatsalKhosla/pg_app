import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getFormatter, getMessages, getTranslations } from "next-intl/server";

import { SearchExperience } from "@/components/search/search-experience";
import { SearchProviders } from "@/components/search/providers";
import { getSearchPage, getSearchReference } from "@/lib/api/public";
import { loadSearchParams, searchQuery } from "@/lib/search/params";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Search");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/search" },
  };
}

/** This month and the next six, in India, as search has prices for (ADR 0027). */
function moveInMonths(format: Awaited<ReturnType<typeof getFormatter>>) {
  const now = new Date();
  const [year, month] = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
  })
    .format(now)
    .split("-")
    .map(Number) as [number, number];
  return Array.from({ length: 7 }, (_, offset) => {
    const date = new Date(Date.UTC(year, month - 1 + offset, 1));
    return {
      value: `${String(date.getUTCFullYear())}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`,
      label: format.dateTime(date, { month: "long", year: "numeric", timeZone: "UTC" }),
    };
  });
}

/**
 * Search (ARCHITECTURE §10.3; step 3.5, ADR 0031): the list and the map of live PGs. The first
 * page of results is rendered here from the URL, so a shared link shows them at once; after that
 * the browser asks the API itself as the filters or the map move, and the URL keeps up.
 */
export default async function SearchPage({ searchParams }: PageProps<"/search">) {
  const state = loadSearchParams(await searchParams);
  const [first, reference] = await Promise.all([
    getSearchPage(searchQuery(state)),
    getSearchReference(),
  ]);
  const t = await getTranslations("Search");
  const messages = await getMessages();
  const format = await getFormatter();

  return (
    <NextIntlClientProvider
      messages={{
        Search: messages.Search,
        Pg: {
          gender: messages.Pg.gender,
          meals: messages.Pg.meals,
          rooms: { sharing: messages.Pg.rooms.sharing },
        },
      }}
    >
      <SearchProviders>
        <h1 className="sr-only">{t("title")}</h1>
        <SearchExperience
          initial={"page" in first ? first.page : null}
          initialProblem={"problem" in first ? first.problem : null}
          campuses={reference.campuses.map((campus) => ({
            slug: campus.slug,
            name: campus.name,
            location: campus.location,
          }))}
          localities={reference.localities.map((locality) => ({
            slug: locality.slug,
            name: locality.name,
            center: locality.center,
          }))}
          stations={reference.stations.map((station) => ({
            slug: station.slug,
            name: station.name,
            location: station.location,
          }))}
          amenities={reference.amenities}
          months={moveInMonths(format)}
        />
      </SearchProviders>
    </NextIntlClientProvider>
  );
}
