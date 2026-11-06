import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A placeholder in the shape of content that is still loading, so the page doesn't jump when it
 * arrives (CLS). Hidden from screen readers: announce loading on the region instead (aria-busy).
 * The pulse stops for people who prefer reduced motion.
 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn("animate-pulse rounded-lg bg-muted motion-reduce:animate-none", className)}
      {...props}
    />
  );
}

export { Skeleton };
