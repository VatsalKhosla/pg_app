import type { Metadata, Route } from "next";
import Image from "next/image";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { isListingStatus, LISTING_STATUSES } from "@/components/ops/choices";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_LISTINGS_PATH, OPS_NEW_LISTING_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;
const SEARCH_MAX = 100;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.listings");
  return { title: t("title") };
}

/** This page with the given filters; empty ones are left out. */
function pageUrl(filters: { status?: string | undefined; q?: string; cursor?: string }): Route {
  const query = new URLSearchParams(
    Object.entries(filters).filter((entry): entry is [string, string] => Boolean(entry[1])),
  ).toString();
  return query === "" ? OPS_LISTINGS_PATH : `${OPS_LISTINGS_PATH}?${query}`;
}

/** Every listing, oldest first, by status or by a name or the owner's phone. */
export default async function OpsListingsPage({ searchParams }: PageProps<"/ops/listings">) {
  await requireOps(OPS_LISTINGS_PATH);
  const params = await searchParams;
  const status = isListingStatus(params.status) ? params.status : undefined;
  const q = typeof params.q === "string" ? params.q.trim().slice(0, SEARCH_MAX) : "";
  const cursor =
    typeof params.cursor === "string" && UUID.test(params.cursor) ? params.cursor : undefined;
  const api = await getServerApi();
  const page = await unwrap(
    api.GET("/v1/ops/properties", {
      params: { query: { status, q: q === "" ? undefined : q, cursor, limit: PAGE_SIZE } },
    }),
  );
  const t = await getTranslations("Ops");
  const format = await getFormatter();

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("listings.title")}</h1>
          <p className="text-muted-foreground">{t("listings.intro")}</p>
        </div>
        <Link href={OPS_NEW_LISTING_PATH} className={buttonVariants({ size: "lg" })}>
          {t("nav.newListing")}
        </Link>
      </div>

      <div className="space-y-4">
        <nav aria-label={t("listings.statusFilter")} className="flex flex-wrap gap-2">
          {[undefined, ...LISTING_STATUSES].map((value) => (
            <Link
              key={value ?? "all"}
              href={pageUrl({ status: value, q })}
              aria-current={value === status ? "page" : undefined}
              className={cn(
                "rounded-full border px-3 py-1 text-sm",
                value === status && "border-primary bg-primary text-primary-foreground",
              )}
            >
              {value === undefined ? t("listings.all") : t(`status.${value}`)}
            </Link>
          ))}
        </nav>
        <form role="search" method="get" action={OPS_LISTINGS_PATH} className="flex gap-2">
          {status === undefined ? null : <input type="hidden" name="status" value={status} />}
          <label htmlFor="listing-search" className="sr-only">
            {t("listings.search")}
          </label>
          <Input
            id="listing-search"
            type="search"
            name="q"
            defaultValue={q}
            maxLength={SEARCH_MAX}
            placeholder={t("listings.search")}
          />
          <Button type="submit" variant="secondary" size="lg">
            {t("listings.searchButton")}
          </Button>
        </form>
      </div>

      {page.items.length === 0 ? (
        <p className="text-muted-foreground">{t("listings.empty")}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {page.items.map((item) => {
            const picture = item.cover?.renditions.find(
              (rendition) => rendition.name === "thumb" && rendition.contentType === "image/webp",
            );
            return (
              <li key={item.id}>
                <Link
                  href={`/ops/listings/${item.id}` as Route}
                  className="flex items-center gap-4 p-3 hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  <div className="relative size-16 shrink-0 overflow-hidden rounded bg-muted">
                    {picture === undefined ? null : (
                      <Image
                        src={picture.url}
                        alt=""
                        fill
                        unoptimized
                        sizes="64px"
                        className="object-cover"
                      />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{item.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {item.locality.name} · {t(`verification.${item.verificationStatus}`)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {t("listings.updated", {
                        when: format.dateTime(new Date(item.updatedAt), {
                          dateStyle: "medium",
                          timeStyle: "short",
                        }),
                      })}
                    </p>
                  </div>
                  <span className="shrink-0 rounded-full border px-2 py-0.5 text-xs">
                    {t(`status.${item.status}`)}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      <div className="flex flex-wrap gap-4">
        {cursor === undefined ? null : (
          <Link href={pageUrl({ status, q })} className={buttonVariants({ variant: "outline" })}>
            {t("listings.first")}
          </Link>
        )}
        {page.nextCursor === null ? null : (
          <Link
            href={pageUrl({ status, q, cursor: page.nextCursor })}
            className={buttonVariants({ variant: "outline" })}
          >
            {t("listings.next")}
          </Link>
        )}
      </div>
    </div>
  );
}
