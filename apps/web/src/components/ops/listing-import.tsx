"use client";

import { useTranslations } from "next-intl";
import type { Route } from "next";
import Link from "next/link";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { FormOutcome } from "@/components/ui/fields";
import { importListings, type ListingImportReport } from "@/lib/ops/client";
import { cn } from "@/lib/utils";

import { useOpsProblem } from "./problems";

const TONES: Record<string, string> = {
  new: "border-neem-border bg-neem-soft text-neem-soft-foreground",
  existing: "border-border/80 bg-surface text-muted-foreground",
  exists: "border-border/80 bg-surface text-muted-foreground",
  needs_pin: "border-marigold-border bg-marigold-soft text-marigold-soft-foreground",
  skipped: "border-ember-border bg-ember-soft text-ember-soft-foreground",
  failed: "border-ember-border bg-ember-soft text-ember-soft-foreground",
};

/**
 * Owners and their PGs from a filled-in template (ADR 0072): pick or paste the file, check it
 * (which makes nothing), then import. Each PG says what became of it, with a way to its draft.
 */
export function ListingImport() {
  const t = useTranslations("Ops.import");
  const problem = useOpsProblem();
  const id = useId();
  const [text, setText] = useState("");
  const [report, setReport] = useState<ListingImportReport | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(dryRun: boolean) {
    setFailure(null);
    setBusy(true);
    try {
      setReport(await importListings(text, dryRun));
    } catch (error) {
      setFailure(problem(error));
    } finally {
      setBusy(false);
    }
  }

  const ready = report !== null && !report.done && report.pgs.length > 0;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <label htmlFor={`${id}-file`} className="block text-sm font-medium">
          {t("file")}
        </label>
        <input
          id={`${id}-file`}
          type="file"
          accept=".csv,text/csv"
          className="block w-full text-sm file:mr-3 file:rounded-full file:border-0 file:bg-primary-soft file:px-4 file:py-2 file:font-semibold file:text-primary-soft-foreground"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file === undefined) return;
            void file.text().then((read) => {
              setText(read);
              setReport(null);
            });
          }}
        />
      </div>
      <div className="space-y-2">
        <label htmlFor={`${id}-text`} className="block text-sm font-medium">
          {t("paste")}
        </label>
        <textarea
          id={`${id}-text`}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setReport(null);
          }}
          rows={8}
          spellCheck={false}
          className="w-full rounded-xl border border-input bg-background p-3 font-mono text-xs"
        />
      </div>
      <FormOutcome failure={failure} />
      <div className="flex flex-wrap gap-3">
        <Button
          type="button"
          size="lg"
          variant="secondary"
          disabled={busy || text.trim() === ""}
          onClick={() => {
            void send(true);
          }}
        >
          {busy ? t("working") : t("check")}
        </Button>
        <Button
          type="button"
          size="lg"
          disabled={busy || !ready}
          onClick={() => {
            void send(false);
          }}
        >
          {t("import")}
        </Button>
      </div>
      {report === null ? null : (
        <section aria-labelledby={`${id}-result`} className="space-y-3">
          <h2 id={`${id}-result`} className="text-title-3 font-semibold tracking-tight">
            {report.done ? t("doneTitle") : t("checkTitle")}
          </h2>
          {report.problems.length === 0 ? null : (
            <ul className="space-y-1 rounded-xl border border-ember-border bg-ember-soft p-4 text-sm text-ember-soft-foreground">
              {report.problems.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
          {report.pgs.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("nothing")}</p>
          ) : (
            <ul className="space-y-3">
              {report.pgs.map((pg) => (
                <li
                  key={`${String(pg.row)}-${pg.name}`}
                  className="space-y-2 rounded-2xl border border-border/80 bg-card p-4 shadow-xs"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="font-semibold">
                      {pg.listingId !== null && report.done ? (
                        <Link
                          href={`/ops/listings/${pg.listingId}` as Route}
                          className="text-primary underline underline-offset-4"
                        >
                          {pg.name}
                        </Link>
                      ) : (
                        pg.name
                      )}
                    </p>
                    <span className="text-sm text-muted-foreground">
                      {t("row", { row: pg.row, owner: pg.ownerName })}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs font-semibold">
                    <span className={cn("rounded-full border px-2.5 py-0.5", TONES[pg.owner])}>
                      {t(`owner.${pg.owner}`)}
                    </span>
                    <span className={cn("rounded-full border px-2.5 py-0.5", TONES[pg.listing])}>
                      {t(`listing.${pg.listing}`, { count: pg.roomTypes })}
                    </span>
                  </div>
                  {pg.problems.length === 0 ? null : (
                    <ul className="list-disc space-y-0.5 pl-5 text-sm text-destructive">
                      {pg.problems.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
