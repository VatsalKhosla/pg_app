import { ArrowRight, type LucideIcon } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * The owner's overview (ADR 0071), in pieces the home page lays out. Every number comes from the
 * API, already worked out there; these only show it.
 */

/** One number that matters, with what it means under it. */
export function StatTile({
  label,
  value,
  note,
  Icon,
  tone,
}: {
  label: string;
  value: string;
  note?: string | undefined;
  Icon: LucideIcon;
  /** The icon's colour: the site's evening colours, one per kind of number. */
  tone: "primary" | "marigold" | "dusk" | "neem";
}) {
  return (
    <div className="flex h-full flex-col gap-3 rounded-[1.5rem] border border-border/70 bg-card p-5 shadow-md">
      <span
        aria-hidden="true"
        className={cn(
          "grid size-10 place-items-center rounded-xl shadow-sm",
          tone === "primary" && "bg-primary-soft text-primary-soft-foreground",
          tone === "marigold" && "bg-marigold-soft text-marigold-soft-foreground",
          tone === "dusk" && "bg-dusk-soft text-dusk-soft-foreground",
          tone === "neem" && "bg-neem-soft text-neem-soft-foreground",
        )}
      >
        <Icon className="size-5" />
      </span>
      <div className="space-y-1">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        <p className="text-title-2 font-semibold tracking-tight text-foreground tabular-nums">
          {value}
        </p>
        {note === undefined ? null : <p className="text-sm text-muted-foreground">{note}</p>}
      </div>
    </div>
  );
}

/** Something that waits for the owner, as a way straight to it. */
export function NeedsYouCard({
  href,
  title,
  detail,
  Icon,
  urgent,
}: {
  href: Route;
  title: string;
  detail?: string | undefined;
  Icon: LucideIcon;
  urgent: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "group flex h-full items-start gap-4 rounded-[1.5rem] border p-5 shadow-sm outline-none transition-[box-shadow,transform] duration-(--duration-base) ease-standard hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        urgent
          ? "border-marigold-border bg-marigold-soft text-marigold-soft-foreground"
          : "border-border/70 bg-card text-card-foreground",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "grid size-10 shrink-0 place-items-center rounded-xl",
          urgent ? "bg-sun text-sun-foreground" : "bg-primary-soft text-primary-soft-foreground",
        )}
      >
        <Icon className="size-5" />
      </span>
      <span className="min-w-0 flex-1 space-y-1">
        <span className="block font-semibold">{title}</span>
        {detail === undefined ? null : (
          <span className={cn("block text-sm", !urgent && "text-muted-foreground")}>{detail}</span>
        )}
      </span>
      <ArrowRight
        aria-hidden="true"
        className="mt-1 size-4 shrink-0 transition-transform duration-(--duration-base) group-hover:translate-x-1 motion-reduce:transition-none"
      />
    </Link>
  );
}

export interface PgBeds {
  id: string;
  href: Route;
  name: string;
  /** Its locality and status, already worded. */
  place: string;
  beds: number;
  taken: number;
  /** "18 of 20 beds", already worded. */
  words: string;
}

/** Each PG's beds as a bar: how much of it is taken today. */
export function BedsByPg({ label, pgs }: { label: string; pgs: readonly PgBeds[] }) {
  return (
    <ul aria-label={label} className="space-y-5">
      {pgs.map((pg) => {
        const share = pg.beds > 0 ? Math.min(pg.taken / pg.beds, 1) : 0;
        return (
          <li key={pg.id} className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <Link
                href={pg.href}
                className="font-semibold text-foreground underline-offset-4 outline-none hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring"
              >
                {pg.name}
              </Link>
              <span className="text-sm font-medium text-foreground tabular-nums">{pg.words}</span>
            </div>
            <div aria-hidden="true" className="share-bar-track h-2.5 overflow-hidden rounded-full">
              {share > 0 ? (
                <div
                  className="share-bar-fill h-full rounded-full"
                  style={{ width: `${(share * 100).toFixed(1)}%` }}
                />
              ) : null}
            </div>
            <p className="text-sm text-muted-foreground">{pg.place}</p>
          </li>
        );
      })}
    </ul>
  );
}
