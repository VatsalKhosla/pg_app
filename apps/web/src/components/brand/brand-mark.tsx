import { brandInitial } from "@/config/brand";
import { cn } from "@/lib/utils";

/** The brand's square mark: its initial on an ink evening, with the sun going down behind it. It matches the app icons. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "relative grid size-9 place-items-center overflow-hidden rounded-xl bg-night font-display text-lg leading-none font-semibold text-night-foreground shadow-sm ring-1 ring-night-border",
        className,
      )}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute -right-1 -bottom-2 size-5 rounded-full bg-sun"
      />
      <span className="relative">{brandInitial}</span>
    </span>
  );
}
