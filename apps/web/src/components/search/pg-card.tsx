import { ShieldCheck } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { type ComponentProps, ViewTransition } from "react";

import { ListingPlaceholderArt } from "@/components/brand/editorial-art";
import { Photo } from "@/components/pg/photo";
import { Badge } from "@/components/ui/badge";
import { formatDistance } from "@/lib/format/distance";
import { formatINR } from "@/lib/money";
import type { SearchCard } from "@/lib/search/client";
import { cn } from "@/lib/utils";

type Handlers = Pick<
  ComponentProps<typeof Link>,
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
        "group block rounded-[1.75rem] text-card-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4 focus-visible:ring-offset-background",
        active && "ring-2 ring-primary ring-offset-4 ring-offset-background",
      )}
    >
      <div className="relative aspect-4/3 overflow-hidden rounded-[1.75rem] bg-marigold-soft">
        {card.cover === null ? (
          <ListingPlaceholderArt />
        ) : (
          <ViewTransition name={`pg-photo-${card.id}`}>
            <Photo
              media={card.cover}
              alt=""
              sizes="(min-width: 1280px) 17rem, (min-width: 640px) 50vw, 100vw"
              first={first}
              cardOnly
              className="h-full w-full object-cover transition-transform duration-(--duration-slower) ease-emphasized group-hover:scale-[1.04] motion-reduce:transition-none motion-reduce:group-hover:scale-100"
            />
          </ViewTransition>
        )}
        <p className="absolute top-3 left-3 flex flex-wrap gap-1.5 pr-3">
          {card.verified ? (
            <Badge variant="overlay">
              <ShieldCheck aria-hidden="true" className="size-3.5 text-neem" />
              {t("verified")}
            </Badge>
          ) : null}
          {card.licensed ? <Badge variant="overlay">{t("licensed")}</Badge> : null}
        </p>
      </div>
      <div className="space-y-1 px-1.5 pt-3 pb-1">
        <p className="font-display text-lg leading-snug font-medium text-foreground">{card.name}</p>
        <p className="text-sm text-muted-foreground">
          {[
            card.locality.name,
            tPg(`gender.${card.genderPolicy}`),
            tPg(`meals.${card.meals}`),
          ].join(" · ")}
        </p>
        {card.distanceM === null && card.nearestStation === null ? null : (
          <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-muted-foreground">
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
        <p className="pt-1 text-base font-semibold text-foreground tabular-nums">{price}</p>
        <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-sm">
          <span className="font-medium text-neem">{t("refundable")}</span>
          <span className="text-muted-foreground">{t(`beds.${card.bedsFree}`)}</span>
        </p>
      </div>
    </Link>
  );
}
