import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

const tones = {
  violet:
    "from-primary to-[color-mix(in_oklch,var(--primary)_55%,var(--ember))] text-primary-foreground",
  sun: "from-sun to-[color-mix(in_oklch,var(--sun)_60%,var(--ember))] text-sun-foreground",
  teal: "from-dusk to-[color-mix(in_oklch,var(--dusk)_60%,var(--primary))] text-white dark:text-night",
  green:
    "from-neem to-[color-mix(in_oklch,var(--neem)_60%,var(--dusk))] text-white dark:text-night",
  rose: "from-ember to-[color-mix(in_oklch,var(--ember)_60%,var(--sun))] text-white dark:text-night",
} as const;

export type FeatureTone = keyof typeof tones;

/** A point a page makes: a bright icon, a short heading and a plain sentence or two. */
export function FeatureCard({
  icon: Icon,
  tone = "violet",
  title,
  children,
}: {
  icon: LucideIcon;
  tone?: FeatureTone;
  title: string;
  children: ReactNode;
}) {
  return (
    <li className="group relative flex flex-col gap-4 rounded-[1.75rem] border border-border/70 bg-card p-6 shadow-md transition-[transform,box-shadow] duration-(--duration-base) ease-standard hover:-translate-y-1 hover:shadow-xl motion-reduce:transition-none motion-reduce:hover:translate-y-0 sm:p-7">
      <span
        aria-hidden="true"
        className={`grid size-13 place-items-center rounded-2xl bg-linear-to-br shadow-md ${tones[tone]}`}
      >
        <Icon className="size-6" />
      </span>
      <h3 className="text-title-3 font-medium text-foreground">{title}</h3>
      <div className="leading-relaxed text-muted-foreground">{children}</div>
    </li>
  );
}

export function FeatureGrid({ children }: { children: ReactNode }) {
  return <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{children}</ul>;
}
