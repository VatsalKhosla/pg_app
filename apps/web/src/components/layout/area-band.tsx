import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/**
 * The top of a working area (the ops console, the owner area, field visits and admin): the dusk
 * band the account page opens with, the area's name beside its icon, and its navigation, so every
 * page in the area opens the same way. The page's own heading stays the page's h1.
 */
export function AreaBand({
  eyebrow,
  title,
  Icon,
  children,
}: {
  eyebrow: string;
  title: string;
  Icon: LucideIcon;
  children: ReactNode;
}) {
  return (
    <header className="scope-night relative isolate overflow-hidden rounded-[1.75rem] p-4 shadow-lg sm:rounded-[2rem] sm:p-6">
      <div aria-hidden="true" className="sky-band absolute inset-0 -z-10" />
      <div className="flex items-center gap-4">
        <span
          aria-hidden="true"
          className="grid size-11 shrink-0 place-items-center rounded-2xl bg-sun text-sun-foreground shadow-md sm:size-12"
        >
          <Icon className="size-5 sm:size-6" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-medium text-night-foreground">{eyebrow}</p>
          <p className="text-title-3 font-semibold tracking-tight text-balance sm:text-title-2">
            {title}
          </p>
        </div>
      </div>
      <div className="mt-4 sm:mt-5">{children}</div>
    </header>
  );
}
