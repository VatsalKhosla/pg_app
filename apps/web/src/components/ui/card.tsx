import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

// shadcn/ui's card, on the design tokens. `flat` is a bordered panel for working screens (owner,
// ops); `raised` floats on a soft shadow; `interactive` is for a card that is itself a link (a PG in
// the results): it lifts under the pointer, and its focus ring wraps the whole card. Put the link on
// the card with `asChild` so the card is one target, not a nest of them.
const cardVariants = cva(
  "flex flex-col rounded-xl border bg-card text-card-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
  {
    variants: {
      variant: {
        flat: "",
        raised: "border-border/70 shadow-md dark:border-border",
        interactive:
          "transition-[box-shadow,border-color,transform] duration-(--duration-base) ease-standard hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg motion-reduce:transition-none motion-reduce:hover:translate-y-0 dark:hover:border-border",
        warm: "border-marigold-border bg-surface-warm shadow-xs",
        ink: "border-primary/30 bg-primary-soft shadow-xs",
        ember: "border-ember-border bg-ember-soft shadow-xs",
        marigold: "border-marigold-border bg-marigold-soft shadow-xs",
        dusk: "border-dusk-border bg-dusk-soft shadow-xs",
        neem: "border-neem-border bg-neem-soft shadow-xs",
      },
    },
    defaultVariants: { variant: "flat" },
  },
);

type CardProps = React.ComponentProps<"div"> &
  VariantProps<typeof cardVariants> & {
    /** Render the child element (a link or an article) with the card's styles. */
    asChild?: boolean;
  };

function Card({ className, variant, asChild = false, ...props }: CardProps) {
  const Component = asChild ? Slot.Root : "div";
  return (
    <Component data-slot="card" className={cn(cardVariants({ variant, className }))} {...props} />
  );
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn("flex flex-col gap-1.5 p-5 sm:p-6", className)}
      {...props}
    />
  );
}

/**
 * The card's title. It renders a <div>: pass the heading of the right level with `asChild`
 * (`<CardTitle asChild><h2>…</h2></CardTitle>`) so the page's headings stay in order.
 */
function CardTitle({
  className,
  asChild = false,
  ...props
}: React.ComponentProps<"div"> & { asChild?: boolean }) {
  const Component = asChild ? Slot.Root : "div";
  return (
    <Component
      data-slot="card-title"
      className={cn("font-display text-lg leading-snug font-semibold tracking-tight", className)}
      {...props}
    />
  );
}

function CardDescription({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="card-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-5 pb-5 first:pt-5 sm:px-6 sm:pb-6 sm:first:pt-6", className)}
      {...props}
    />
  );
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn("mt-auto flex items-center gap-3 border-t px-5 py-4 sm:px-6", className)}
      {...props}
    />
  );
}

export { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle, cardVariants };
