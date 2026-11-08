"use client";

import type { InfiniteData, UseInfiniteQueryResult } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/errors";
import { DEFAULT_STAY } from "@/lib/pricing/calendar";
import type { SearchPage } from "@/lib/search/client";
import { cn } from "@/lib/utils";

import { ResultCard } from "./result-card";

export type ResultsQuery = UseInfiniteQueryResult<InfiniteData<SearchPage>>;

/** Why a search can't be answered, in the API's words (422 SEARCH_INVALID), or null. */
export function searchProblem(results: ResultsQuery): string | null {
  const { error } = results;
  if (!(error instanceof ApiError) || error.status !== 422) return null;
  return error.problem?.detail ?? error.message;
}

/**
 * The results as a list: what the map shows, for everyone, keyboard and screen reader users
 * included (ARCHITECTURE §10.3). Each state says what's happening: loading, nothing found, a
 * search the API can't answer, a failure, or the PGs a page at a time.
 */
export function Results({
  results,
  problem,
  hoveredId,
  onHover,
  onClear,
  className,
}: {
  results: ResultsQuery;
  /** A search the page already knows can't be answered. */
  problem: string | null;
  hoveredId: string | null;
  onHover: (id: string | null) => void;
  onClear: () => void;
  className?: string;
}) {
  const t = useTranslations("Search");
  const invalid = problem ?? searchProblem(results);
  const cards = results.data?.pages.flatMap((page) => page.items) ?? [];

  if (invalid !== null) {
    return (
      <Card role="alert" variant="flat" className={cn("space-y-3 rounded-2xl p-5", className)}>
        <p className="font-semibold text-foreground">{t("results.invalid")}</p>
        <p className="text-sm text-muted-foreground">{invalid}</p>
        <div>
          <Button variant="outline" shape="pill" onClick={onClear}>
            {t("filters.clear")}
          </Button>
        </div>
      </Card>
    );
  }
  if (results.isPending) {
    return (
      <div className={className}>
        <p role="status" className="mb-3 text-sm font-medium text-muted-foreground">
          {t("results.loading")}
        </p>
        <ul aria-hidden="true" className="grid gap-x-4 gap-y-7 sm:grid-cols-2">
          {[0, 1, 2, 3].map((index) => (
            <li key={index}>
              <Skeleton className="aspect-4/3 rounded-[1.75rem]" />
              <div className="space-y-2.5 px-1.5 pt-3">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3.5 w-1/2" />
                <Skeleton className="h-4 w-1/3" />
              </div>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (results.isError && cards.length === 0) {
    return (
      <Card role="alert" variant="flat" className={cn("space-y-3 rounded-2xl p-5", className)}>
        <p className="font-medium text-foreground">{t("results.failed")}</p>
        <div>
          <Button variant="outline" shape="pill" onClick={() => void results.refetch()}>
            {t("results.retry")}
          </Button>
        </div>
      </Card>
    );
  }
  if (cards.length === 0) {
    return (
      <div
        className={cn(
          "space-y-3 rounded-2xl border border-dashed bg-surface p-8 text-center",
          className,
        )}
      >
        <p role="status" className="font-display text-base font-semibold text-foreground">
          {t("results.none")}
        </p>
        <p className="text-sm text-muted-foreground">{t("results.noneHint")}</p>
        <div className="pt-1">
          <Button variant="outline" shape="pill" onClick={onClear}>
            {t("filters.clear")}
          </Button>
        </div>
      </div>
    );
  }

  const refreshing =
    results.isPlaceholderData || (results.isRefetching && !results.isFetchingNextPage);
  return (
    <div className={className}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p role="status" className="text-sm font-semibold text-foreground">
          {t("results.count", { count: cards.length, more: String(results.hasNextPage) })}
          {refreshing ? (
            <span className="ms-2 font-normal text-muted-foreground">{t("results.loading")}</span>
          ) : null}
        </p>
        {/* The engine prices a month's move-ins for a stay (ADR 0042): say which. */}
        <p className="text-xs text-muted-foreground">
          {t("results.rents", { months: DEFAULT_STAY })}
        </p>
      </div>
      <ul
        aria-busy={refreshing}
        className={cn(
          "grid gap-x-4 gap-y-7 transition-opacity sm:grid-cols-2 motion-reduce:transition-none",
          refreshing && "opacity-60",
        )}
      >
        {cards.map((card, index) => (
          <li key={card.id}>
            <ResultCard
              card={card}
              active={card.id === hoveredId}
              onHover={onHover}
              first={index === 0}
            />
          </li>
        ))}
      </ul>
      {results.hasNextPage ? (
        <Button
          variant="outline"
          shape="pill"
          size="lg"
          className="mt-5 w-full"
          disabled={results.isFetchingNextPage}
          onClick={() => void results.fetchNextPage()}
        >
          {results.isFetchingNextPage ? t("results.loadingMore") : t("results.loadMore")}
        </Button>
      ) : null}
      {results.isError ? (
        <p role="alert" className="mt-3 text-sm font-medium text-destructive">
          {t("results.failed")}
        </p>
      ) : null}
    </div>
  );
}
