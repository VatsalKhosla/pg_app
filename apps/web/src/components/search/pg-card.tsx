import { ShieldCheck } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type * as React from "react";

import { Photo } from "@/components/pg/photo";
import { Badge } from "@/components/ui/badge";
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
        "group flex gap-3.5 rounded-2xl border bg-card p-3.5 text-card-foreground shadow-xs transition-[box-shadow,border-color,background-color,transform] duration-(--duration-base) ease-standard outline-none hover:-translate-y-0.5 hover:border-foreground/30 hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        active && "border-primary bg-primary-soft/50 shadow-md ring-1 ring-primary",
      )}
    >
      <div className="relative size-26 shrink-0 overflow-hidden rounded-xl bg-muted sm:size-30">
        {card.cover === null ? null : (
          <Photo
            media={card.cover}
            alt=""
            sizes="120px"
            first={first}
            className="h-full w-full object-cover transition-transform duration-(--duration-slow) ease-emphasized group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100"
          />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col justify-between gap-1 py-0.5">
        <div className="space-y-0.5">
          <p className="font-display text-base leading-snug font-semibold tracking-tight text-foreground">
            {card.name}
          </p>
          <p className="text-xs font-medium text-muted-foreground sm:text-sm">
            {[
              card.locality.name,
              tPg(`gender.${card.genderPolicy}`),
              tPg(`meals.${card.meals}`),
            ].join(" · ")}
          </p>
        </div>
        <p className="text-base font-bold tracking-tight text-foreground">{price}</p>
        {card.distanceM === null && card.nearestStation === null ? null : (
          <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
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
        )}
        <p className="flex flex-wrap items-center gap-1.5 pt-0.5 text-xs">
          {card.verified ? (
            <Badge variant="brand" className="px-2 py-0 text-[11px]">
              <ShieldCheck aria-hidden="true" className="size-3" />
              {t("verified")}
            </Badge>
          ) : null}
          {card.licensed ? (
            <Badge variant="outline" className="px-2 py-0 text-[11px]">
              {t("licensed")}
            </Badge>
          ) : null}
          <span className="font-medium text-muted-foreground">{t(`beds.${card.bedsFree}`)}</span>
        </p>
      </div>
    </Link>
  );
}
