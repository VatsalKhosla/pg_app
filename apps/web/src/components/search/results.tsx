"use client";

import type { InfiniteData, UseInfiniteQueryResult } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import type { SearchPage } from "@/lib/search/client";
import { cn } from "@/lib/utils";
import { DEFAULT_STAY } from "@/lib/pricing/calendar";

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
      <div role="alert" className={cn("space-y-3 rounded-lg border p-4", className)}>
        <p className="font-medium">{t("results.invalid")}</p>
        <p className="text-sm text-muted-foreground">{invalid}</p>
        <Button variant="outline" onClick={onClear}>
          {t("filters.clear")}
        </Button>
      </div>
    );
  }
  if (results.isPending) {
    return (
      <div className={className}>
        <p role="status" className="mb-3 text-sm text-muted-foreground">
          {t("results.loading")}
        </p>
        <ul aria-hidden="true" className="space-y-3">
          {[0, 1, 2, 3].map((index) => (
            <li key={index} className="flex gap-3 rounded-lg border p-3 motion-safe:animate-pulse">
              <div className="size-24 shrink-0 rounded-md bg-muted sm:size-28" />
              <div className="flex-1 space-y-2 py-1">
                <div className="h-4 w-3/4 rounded bg-muted" />
                <div className="h-3 w-1/2 rounded bg-muted" />
                <div className="h-4 w-1/3 rounded bg-muted" />
              </div>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (results.isError && cards.length === 0) {
    return (
      <div role="alert" className={cn("space-y-3 rounded-lg border p-4", className)}>
        <p>{t("results.failed")}</p>
        <Button variant="outline" onClick={() => void results.refetch()}>
          {t("results.retry")}
        </Button>
      </div>
    );
  }
  if (cards.length === 0) {
    return (
      <div className={cn("space-y-3 rounded-lg border border-dashed p-6 text-center", className)}>
        <p role="status" className="font-medium">
          {t("results.none")}
        </p>
        <p className="text-sm text-muted-foreground">{t("results.noneHint")}</p>
        <Button variant="outline" onClick={onClear}>
          {t("filters.clear")}
        </Button>
      </div>
    );
  }

  const refreshing =
    results.isPlaceholderData || (results.isRefetching && !results.isFetchingNextPage);
  return (
    <div className={className}>
      <p role="status" className="text-sm text-muted-foreground">
        {t("results.count", { count: cards.length, more: String(results.hasNextPage) })}
        {refreshing ? <span className="ms-2">{t("results.loading")}</span> : null}
      </p>
      {/* The engine prices a month's move-ins for a stay (ADR 0042): say which. */}
      <p className="mb-3 text-sm text-muted-foreground">
        {t("results.rents", { months: DEFAULT_STAY })}
      </p>
      <ul
        aria-busy={refreshing}
        className={cn(
          "space-y-3 transition-opacity motion-reduce:transition-none",
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
          className="mt-4 w-full"
          disabled={results.isFetchingNextPage}
          onClick={() => void results.fetchNextPage()}
        >
          {results.isFetchingNextPage ? t("results.loadingMore") : t("results.loadMore")}
        </Button>
      ) : null}
      {results.isError ? (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {t("results.failed")}
        </p>
      ) : null}
    </div>
  );
}
