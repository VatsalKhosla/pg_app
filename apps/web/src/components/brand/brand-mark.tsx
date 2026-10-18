import { brandInitial } from "@/config/brand";
import { cn } from "@/lib/utils";

/** The brand's square mark (its initial on the primary colour), matching the app icons. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-8 place-items-center rounded-lg bg-primary text-base leading-none font-bold text-primary-foreground",
        className,
      )}
    >
      {brandInitial}
    </span>
  );
}
