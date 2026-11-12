import { TrainFront } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { getSearchPlaces, type SearchPlace } from "@/lib/api/public";
import { formatINR } from "@/lib/money";

// Stops on each line: the places with the most PGs.
const STOPS = 8;

interface Stop {
  key: string;
  href: Route;
  name: string;
  detail: string;
}

/**
 * One line of a Metro map: a coloured line with its name and a train, and each campus or locality
 * with PGs as a station on it, which opens that place's PGs. It scrolls sideways when the stations
 * outrun the screen, with the line running on.
 */
function MetroLine({
  name,
  hint,
  colour,
  stops,
}: {
  name: string;
  hint: string;
  colour: string;
  stops: readonly Stop[];
}) {
  return (
    <div className="min-w-0" style={{ "--line": colour }}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-gutter lg:px-0">
        <span className="inline-flex items-center gap-2 rounded-full bg-(--line) py-1.5 pr-4 pl-1.5 text-sm font-semibold text-white shadow-sm dark:text-night">
          <span className="grid size-7 place-items-center rounded-full bg-white/20">
            <TrainFront aria-hidden="true" className="size-4" />
          </span>
          {name}
        </span>
        <span className="text-sm text-muted-foreground">{hint}</span>
      </div>
      <ol className="metro-track mt-5 flex snap-x scroll-px-gutter overflow-x-auto px-gutter pb-3 [scrollbar-width:none] lg:px-0">
        {stops.map((stop) => (
          <li key={stop.key} className="metro-stop relative w-44 shrink-0 snap-start sm:w-52">
            <Link
              href={stop.href}
              className="group relative block rounded-xl pt-0.5 pr-4 pb-1 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <span aria-hidden="true" className="metro-station" />
              <span className="mt-4 block leading-snug font-semibold group-hover:underline group-hover:underline-offset-4">
                {stop.name}
              </span>
              <span className="mt-0.5 block text-sm text-muted-foreground">{stop.detail}</span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}

/**
 * The campuses and localities with the most PGs (step 3.6), as two Metro lines: for people and
 * search engines alike. Without the API there's nothing to link to, and the page stands without it.
 */
export async function MetroLines() {
  let places: SearchPlace[];
  try {
    places = (await getSearchPlaces()).items;
  } catch {
    return null;
  }
  if (places.length === 0) return null;
  const t = await getTranslations("Home.places");
  const stops = (kind: SearchPlace["kind"], base: string): Stop[] =>
    places
      .filter((place) => place.kind === kind)
      .slice(0, STOPS)
      .map((place) => ({
        key: place.slug,
        href: `${base}/${place.slug}` as Route,
        name: place.name,
        detail: t("stop", { count: place.listings, rent: formatINR(place.minRentPaise) }),
      }));
  const lines = [
    {
      name: t("campusLine"),
      hint: t("campusHint"),
      colour: "var(--primary)",
      stops: stops("campus", "/pg-near"),
    },
    {
      name: t("localityLine"),
      hint: t("localityHint"),
      colour: "var(--dusk)",
      stops: stops("locality", "/pg-in"),
    },
  ].filter((line) => line.stops.length > 0);
  return (
    <section
      aria-labelledby="places-title"
      className="mx-auto w-full max-w-page pt-section lg:px-gutter"
    >
      <h2 id="places-title" className="px-gutter text-display font-medium lg:px-0">
        {t("title")}
      </h2>
      <p className="mt-3 max-w-prose px-gutter text-lg text-muted-foreground lg:px-0">
        {t("lead")}
      </p>
      <div className="mt-10 grid gap-10">
        {lines.map((line) => (
          <MetroLine key={line.name} {...line} />
        ))}
      </div>
    </section>
  );
}
