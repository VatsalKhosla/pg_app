import Image from "next/image";

import logoMark from "@/assets/brand/logo-mark.webp";
import { cn } from "@/lib/utils";

/**
 * The brand's mark: the founders' logo (2026-11-26), a teal house in a gold ring. It matches the
 * app icons. Always beside the brand's name, so it says nothing to a screen reader itself.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <Image
      src={logoMark}
      alt=""
      aria-hidden
      unoptimized
      className={cn("size-9 shrink-0 rounded-full", className)}
    />
  );
}
