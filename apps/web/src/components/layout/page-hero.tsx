import type { LucideIcon } from "lucide-react";

/**
 * A student's own pages open like their account page: the page's heading and what it's for on
 * the dusk band, beside the page's icon.
 */
export function PageHero({
  title,
  intro,
  Icon,
}: {
  title: string;
  intro: string;
  Icon: LucideIcon;
}) {
  return (
    <header className="scope-night relative isolate overflow-hidden rounded-[2rem] p-7 shadow-lg sm:p-10">
      <div aria-hidden="true" className="sky-band absolute inset-0 -z-10" />
      <div className="flex flex-wrap items-center gap-5">
        <span
          aria-hidden="true"
          className="grid size-14 shrink-0 place-items-center rounded-2xl bg-sun text-sun-foreground shadow-lg"
        >
          <Icon className="size-7" />
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <h1 className="text-display font-medium">{title}</h1>
          <p className="max-w-prose text-night-foreground">{intro}</p>
        </div>
      </div>
    </header>
  );
}
