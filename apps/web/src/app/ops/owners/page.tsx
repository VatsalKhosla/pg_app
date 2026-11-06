import type { Metadata, Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { AddOwnerPanel } from "@/components/ops/add-owner-panel";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_OWNERS_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";

const PAGE_SIZE = 20;
const SEARCH_MAX = 100;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.owners");
  return { title: t("title") };
}

/** This page with the given search; empty values are left out. */
function pageUrl(filters: { q?: string; cursor?: string }): Route {
  const query = new URLSearchParams(
    Object.entries(filters).filter((entry): entry is [string, string] => Boolean(entry[1])),
  ).toString();
  return query === "" ? OPS_OWNERS_PATH : `${OPS_OWNERS_PATH}?${query}`;
}

/** Every owner, by phone number or name, with where they stand with the owner agreement. */
export default async function OpsOwnersPage({ searchParams }: PageProps<"/ops/owners">) {
  await requireOps(OPS_OWNERS_PATH);
  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q.trim().slice(0, SEARCH_MAX) : "";
  const cursor =
    typeof params.cursor === "string" && UUID.test(params.cursor) ? params.cursor : undefined;
  const api = await getServerApi();
  const page = await unwrap(
    api.GET("/v1/ops/owners", {
      params: { query: { q: q === "" ? undefined : q, cursor, limit: PAGE_SIZE } },
    }),
  );
  const t = await getTranslations("Ops.owners");

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="font-display text-title-1 text-foreground">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>

      <form role="search" method="get" action={OPS_OWNERS_PATH} className="flex gap-2">
        <label htmlFor="owner-search" className="sr-only">
          {t("search")}
        </label>
        <Input
          id="owner-search"
          type="search"
          name="q"
          defaultValue={q}
          maxLength={SEARCH_MAX}
          placeholder={t("search")}
        />
        <Button type="submit" variant="secondary" size="lg">
          {t("searchButton")}
        </Button>
      </form>

      {page.items.length === 0 ? (
        <p className="text-muted-foreground">{t("empty")}</p>
      ) : (
        <ul className="divide-y divide-border/60 overflow-hidden rounded-2xl border border-border/80 bg-card shadow-xs">
          {page.items.map((owner) => (
            <li key={owner.id}>
              <Link
                href={`/ops/owners/${owner.id}` as Route}
                className="flex flex-wrap items-center justify-between gap-3 p-4 transition-colors hover:bg-surface focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <div className="min-w-0">
                  <p className="truncate font-semibold text-foreground">{owner.businessName}</p>
                  <p className="text-sm text-muted-foreground">
                    {owner.legalName}
                    {owner.phone === null ? null : ` · ${owner.phone}`}
                  </p>
                </div>
                <span className="shrink-0 rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium text-muted-foreground ring-1 ring-border/70">
                  {owner.agreementCurrent ? t("accepted") : t("notAccepted")}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-4">
        {cursor === undefined ? null : (
          <Link href={pageUrl({ q })} className={buttonVariants({ variant: "outline" })}>
            {t("first")}
          </Link>
        )}
        {page.nextCursor === null ? null : (
          <Link
            href={pageUrl({ q, cursor: page.nextCursor })}
            className={buttonVariants({ variant: "outline" })}
          >
            {t("next")}
          </Link>
        )}
      </div>

      <section
        aria-labelledby="add-owner-title"
        className="space-y-4 rounded-2xl border border-border/80 bg-card p-6 shadow-xs"
      >
        <h2 id="add-owner-title" className="font-display text-title-3 text-foreground">
          {t("addTitle")}
        </h2>
        <AddOwnerPanel />
      </section>
    </div>
  );
}
