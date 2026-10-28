"use client";

import { skipToken, useQuery } from "@tanstack/react-query";
import { ShieldCheck, XIcon } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";

import { Photo } from "@/components/pg/photo";
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
        "relative flex gap-3 rounded-xl border bg-background p-3 pe-11 shadow-lg outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
        className,
      )}
    >
      <div className="relative size-20 shrink-0 overflow-hidden rounded-md bg-muted">
        {cover == null ? null : (
          <Photo media={cover} alt="" sizes="80px" className="h-full w-full object-cover" />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        {name === undefined ? (
          <p role="status" className="text-sm text-muted-foreground">
            {t("preview.loading")}
          </p>
        ) : (
          <p className="truncate font-semibold">{name}</p>
        )}
        <p className="truncate text-sm text-muted-foreground">
          {[locality, tPg(`gender.${pin.genderPolicy}`)].filter(Boolean).join(" · ")}
        </p>
        <p className="text-sm font-medium">{price}</p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          {pin.verified ? (
            <span className="inline-flex items-center gap-1 font-medium text-primary">
              <ShieldCheck aria-hidden="true" className="size-3.5" />
              {t("card.verified")}
            </span>
          ) : null}
          <span className="text-muted-foreground">{t(`card.beds.${pin.bedsFree}`)}</span>
        </div>
        <Link
          href={`/pg/${pin.slug}` as Route}
          className={cn(buttonVariants({ size: "sm" }), "mt-1")}
        >
          {t("preview.open")}
        </Link>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="absolute top-2 right-2 grid size-9 place-items-center rounded-md text-muted-foreground outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <XIcon aria-hidden="true" className="size-4" />
        <span className="sr-only">{t("preview.close")}</span>
      </button>
    </section>
  );
}
