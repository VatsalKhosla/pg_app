import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";

const tones = {
  violet:
    "from-primary to-[color-mix(in_oklch,var(--primary)_55%,var(--ember))] text-primary-foreground",
  green:
    "from-neem to-[color-mix(in_oklch,var(--neem)_60%,var(--dusk))] text-white dark:text-night",
  teal: "from-dusk to-[color-mix(in_oklch,var(--dusk)_60%,var(--primary))] text-white dark:text-night",
} as const;

/**
 * A booking's document as a card (ADR 0070): the rent agreement or the police verification, with
 * a bright icon, its title and its status, as the story pages' feature cards are drawn.
 */
export function DocumentCard({
  id,
  icon: Icon,
  tone = "violet",
  title,
  status,
  done = false,
  children,
}: {
  id: string;
  icon: LucideIcon;
  tone?: keyof typeof tones;
  title: string;
  status: string;
  /** Signed, or verified: the status shows as settled. */
  done?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={`${id}-title`}
      className="space-y-5 rounded-[1.75rem] border border-border/70 bg-card p-6 text-card-foreground shadow-md sm:p-7"
    >
      <div className="flex flex-wrap items-center gap-4">
        <span
          aria-hidden="true"
          className={`grid size-13 shrink-0 place-items-center rounded-2xl bg-linear-to-br shadow-md ${tones[tone]}`}
        >
          <Icon className="size-6" />
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <h2 id={`${id}-title`} className="text-title-3 font-semibold text-foreground">
            {title}
          </h2>
          <Badge variant={done ? "success" : "marigold"}>{status}</Badge>
        </div>
      </div>
      {children}
    </section>
  );
}
