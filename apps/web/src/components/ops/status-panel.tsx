"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { type Listing, setStatus } from "@/lib/ops/client";

import type { ListingStatus } from "./choices";
import { FormOutcome } from "@/components/ui/fields";
import { useOpsProblem } from "./problems";
import { useRefresh } from "./use-refresh";

/**
 * Where the listing stands, what stops it going live, and the moves open to it from here: the
 * API says which (its state machine, ADR 0021), so this never offers one it would refuse.
 */
export function StatusPanel({ listing }: { listing: Listing }) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const [moving, setMoving] = useState<ListingStatus | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function move(target: ListingStatus) {
    setFailure(null);
    setMoving(target);
    try {
      await setStatus(listing.id, target);
      refresh();
    } catch (error) {
      setFailure(problem(error));
    } finally {
      setMoving(null);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm">{t("publish.now", { status: t(`status.${listing.status}`) })}</p>
      {listing.problems.length === 0 ? null : (
        <div className="space-y-1">
          <p className="text-sm font-medium">{t("publish.problems")}</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {listing.problems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        {listing.nextStatuses.map((target) => (
          <Button
            key={target}
            type="button"
            size="lg"
            variant={target === "published" ? "default" : "outline"}
            disabled={moving !== null || (target === "published" && listing.problems.length > 0)}
            onClick={() => {
              void move(target);
            }}
          >
            {moving === target ? t("publish.working") : t(`publish.to.${target}`)}
          </Button>
        ))}
      </div>
      <FormOutcome failure={failure} />
    </div>
  );
}
