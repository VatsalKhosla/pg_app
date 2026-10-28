"use client";

import type { Route } from "next";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ShieldCheck } from "lucide-react";

import { Photo } from "@/components/pg/photo";
import { formatDistance } from "@/lib/format/distance";
import { formatINR } from "@/lib/money";
import type { SearchCard } from "@/lib/search/client";
import { cn } from "@/lib/utils";

/**
 * One PG in the results: a link to its page that also lights up its pin on the map. The first
 * card's photo is the page's largest paint, so it loads at once.
 */
export function ResultCard({
  card,
  active,
  onHover,
  first = false,
}: {
  card: SearchCard;
  active: boolean;
  onHover: (id: string | null) => void;
  first?: boolean;
}) {
  const t = useTranslations("Search.card");
  const tPg = useTranslations("Pg");
  const price =
    card.minRentPaise === card.maxRentPaise
      ? t("onePrice", { price: formatINR(card.minRentPaise) })
      : t("price", { min: formatINR(card.minRentPaise), max: formatINR(card.maxRentPaise) });
  return (
    <Link
      href={`/pg/${card.slug}` as Route}
      onMouseEnter={() => {
        onHover(card.id);
      }}
      onMouseLeave={() => {
        onHover(null);
      }}
      onFocus={() => {
        onHover(card.id);
      }}
      onBlur={() => {
        onHover(null);
      }}
      className={cn(
        "flex gap-3 rounded-lg border p-3 transition-colors outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 motion-reduce:transition-none",
        active && "border-primary bg-accent",
      )}
    >
      <div className="relative size-24 shrink-0 overflow-hidden rounded-md bg-muted sm:size-28">
        {card.cover === null ? null : (
          <Photo
            media={card.cover}
            alt=""
            sizes="112px"
            first={first}
            className="h-full w-full object-cover"
          />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-semibold leading-snug">{card.name}</p>
        <p className="text-sm text-muted-foreground">
          {[
            card.locality.name,
            tPg(`gender.${card.genderPolicy}`),
            tPg(`meals.${card.meals}`),
          ].join(" · ")}
        </p>
        <p className="font-medium">{price}</p>
        <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {card.distanceM === null ? null : (
            <span>{t("fromCampus", { distance: formatDistance(card.distanceM) })}</span>
          )}
          {card.nearestStation === null ? null : (
            <span>
              {t("station", {
                name: card.nearestStation.name,
                distance: formatDistance(card.nearestStation.distanceM),
              })}
            </span>
          )}
        </p>
        <p className="flex flex-wrap items-center gap-2 text-xs">
          {card.verified ? (
            <span className="inline-flex items-center gap-1 font-medium text-primary">
              <ShieldCheck aria-hidden="true" className="size-3.5" />
              {t("verified")}
            </span>
          ) : null}
          {card.licensed ? <span>{t("licensed")}</span> : null}
          <span className="text-muted-foreground">{t(`beds.${card.bedsFree}`)}</span>
        </p>
      </div>
    </Link>
  );
}
