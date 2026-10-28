import type { Route } from "next";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ShieldCheck } from "lucide-react";
import type * as React from "react";

import { Photo } from "@/components/pg/photo";
import { formatDistance } from "@/lib/format/distance";
import { formatINR } from "@/lib/money";
import type { SearchCard } from "@/lib/search/client";
import { cn } from "@/lib/utils";

type Handlers = Pick<
  React.ComponentProps<typeof Link>,
  "onMouseEnter" | "onMouseLeave" | "onFocus" | "onBlur"
>;

/**
 * One PG as search and the landing pages list it: a link to its page with its photo, where it
 * is, who it's for, its rents for the month and how many beds are free. Rendered on the server
 * by landing pages, so they ship no script for it; search's list adds hover handlers.
 */
export function PgCard({
  card,
  active = false,
  first = false,
  handlers,
}: {
  card: SearchCard;
  /** Its pin is the one being looked at. */
  active?: boolean;
  /** The page's largest paint: its photo loads at once. */
  first?: boolean;
  handlers?: Handlers;
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
      {...handlers}
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
