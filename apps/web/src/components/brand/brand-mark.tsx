import { brandInitial } from "@/config/brand";
import { cn } from "@/lib/utils";

/** The brand's square mark (its initial on the primary colour with a warm terracotta corner spark), matching the app icons. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "relative grid size-9 place-items-center overflow-hidden rounded-xl bg-primary font-display text-base leading-none font-bold text-primary-foreground shadow-sm ring-1 ring-primary/20",
        className,
      )}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute -top-1.5 -right-1.5 size-3.5 rounded-full bg-saffron opacity-85"
      />
      <span
        aria-hidden
        className="pointer-events-none absolute -bottom-1.5 -left-1.5 size-3 rounded-full bg-coral opacity-75"
      />
      <span className="relative">{brandInitial}</span>
    </span>
  );
}
