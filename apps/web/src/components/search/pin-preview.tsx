"use client";

import { skipToken, useQuery } from "@tanstack/react-query";
import { ShieldCheck, XIcon } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";

import { ListingPlaceholderArt } from "@/components/brand/editorial-art";
import { Photo } from "@/components/pg/photo";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { formatINR } from "@/lib/money";
import { type MapPin, publicListing, type SearchCard } from "@/lib/search/client";
import { cn } from "@/lib/utils";

/**
 * The PG behind a selected pin, over the map: its prices for the month and who it's for come
 * with the pin; its name and photo from the results when they hold it, or else from its page's
 * data. It takes focus when it opens, so a keyboard user lands on it, and Escape closes it.
 */
export function PinPreview({
  pin,
  card,
  onClose,
  className,
}: {
  pin: MapPin;
  card: SearchCard | undefined;
  onClose: () => void;
  className?: string;
}) {
  const t = useTranslations("Search");
  const tPg = useTranslations("Pg");
  const listing = useQuery({
    queryKey: ["listing", pin.slug],
    queryFn: card === undefined ? ({ signal }) => publicListing(pin.slug, signal) : skipToken,
  });
  const name = card?.name ?? listing.data?.name;
  const locality = card?.locality.name ?? listing.data?.locality.name;
  const cover =
    card === undefined
      ? listing.data?.media.find((media) => media.contentType.startsWith("image/"))
      : card.cover;
  const price =
    pin.minRentPaise === pin.maxRentPaise
      ? t("card.onePrice", { price: formatINR(pin.minRentPaise) })
      : t("card.price", { min: formatINR(pin.minRentPaise), max: formatINR(pin.maxRentPaise) });

  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [pin.id]);

  return (
    <section
      ref={ref}
      tabIndex={-1}
      aria-label={name ?? t("preview.loading")}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
      className={cn(
        "relative flex gap-3.5 overflow-hidden rounded-2xl border border-marigold-border bg-card p-3.5 pt-4 pe-12 text-card-foreground shadow-xl outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      <div className="relative size-22 shrink-0 overflow-hidden rounded-xl border border-marigold-border/60 bg-marigold-soft">
        {cover == null ? (
          <ListingPlaceholderArt />
        ) : (
          <Photo media={cover} alt="" sizes="88px" className="h-full w-full object-cover" />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        {name === undefined ? (
          <p role="status" className="text-sm text-muted-foreground">
            {t("preview.loading")}
          </p>
        ) : (
          <p className="truncate font-display text-base font-semibold text-foreground">{name}</p>
        )}
        <p className="truncate text-xs font-medium text-muted-foreground">
          {[locality, tPg(`gender.${pin.genderPolicy}`)].filter(Boolean).join(" · ")}
        </p>
        <p className="w-fit rounded-md bg-primary-soft px-2 py-0.5 text-sm font-bold text-primary-soft-foreground">
          {price}
        </p>
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {pin.verified ? (
            <Badge variant="neem" className="px-2 py-0 text-[11px]">
              <ShieldCheck aria-hidden="true" className="size-3" />
              {t("card.verified")}
            </Badge>
          ) : null}
          <Badge variant="marigold" className="px-2 py-0 text-[11px] font-semibold">
            {t(`card.beds.${pin.bedsFree}`)}
          </Badge>
        </div>
        <Link
          href={`/pg/${pin.slug}` as Route}
          className={cn(buttonVariants({ size: "sm", shape: "pill" }), "mt-1.5")}
        >
          {t("preview.open")}
        </Link>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="absolute top-2.5 right-2.5 grid size-9 place-items-center rounded-full text-muted-foreground transition-colors outline-none hover:bg-secondary hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
      >
        <XIcon aria-hidden="true" className="size-4" />
        <span className="sr-only">{t("preview.close")}</span>
      </button>
    </section>
  );
}
