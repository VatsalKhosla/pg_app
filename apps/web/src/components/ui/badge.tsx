import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

// shadcn/ui's badge: a short label for a state or a fact, like "Verified" or a booking's status.
// Every variant keeps its text at 4.5:1 on its own fill, in both themes. A badge states a fact the
// API returned; it is never a source of urgency or scarcity the data doesn't support (the brief's
// honest-UI rules).
const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1 rounded-full border border-transparent px-2.5 py-0.5 text-xs leading-5 font-medium whitespace-nowrap [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-3.5",
  {
    variants: {
      variant: {
        neutral: "bg-secondary text-secondary-foreground",
        brand: "bg-primary-soft text-primary-soft-foreground",
        success: "bg-success-soft text-success-soft-foreground",
        warning: "bg-warning-soft text-warning-soft-foreground",
        destructive: "bg-destructive-soft text-destructive-soft-foreground",
        outline: "border-border text-foreground",
        /** On top of a photo: a solid light chip, legible over any picture. */
        overlay: "bg-white/95 text-neutral-900 shadow-sm backdrop-blur-sm",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

type BadgeProps = React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & {
    /** Render the child element (a link, say) with the badge's styles. */
    asChild?: boolean;
  };

function Badge({ className, variant, asChild = false, ...props }: BadgeProps) {
  const Component = asChild ? Slot.Root : "span";
  return (
    <Component data-slot="badge" className={cn(badgeVariants({ variant, className }))} {...props} />
  );
}

export { Badge, badgeVariants };
