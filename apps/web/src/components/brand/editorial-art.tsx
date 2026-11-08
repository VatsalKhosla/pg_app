import { cn } from "@/lib/utils";

/**
 * What a PG's card shows until it has a photo: a small flat evening, plainly a drawing and never
 * mistakable for the building. It's decorative, so it's hidden from assistive technology.
 */
export function ListingPlaceholderArt({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 160 120"
      preserveAspectRatio="xMidYMax slice"
      className={cn("listing-placeholder h-full w-full", className)}
    >
      <circle cx="116" cy="74" r="24" fill="var(--brand-sun)" />
      <path
        d="M0 120V84h22v-8h26v18h20V70h30v20h18V78h24v12h20v30z"
        fill="var(--brand-night)"
        opacity="0.92"
      />
      <path d="M58 70h10v-8H58zM96 70h9v-7h-9z" fill="var(--brand-night)" opacity="0.92" />
    </svg>
  );
}
