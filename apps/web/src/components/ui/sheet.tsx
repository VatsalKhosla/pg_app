"use client";

import { XIcon } from "lucide-react";
import { Dialog as SheetPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

// shadcn/ui's sheet: a Radix dialog that slides in from an edge. Radix handles the focus trap,
// Escape, scroll locking and returning focus. The close button's label is a prop so it can be
// translated, and the slide animations are skipped for people who prefer reduced motion.

function Sheet(props: React.ComponentProps<typeof SheetPrimitive.Root>) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />;
}

function SheetTrigger(props: React.ComponentProps<typeof SheetPrimitive.Trigger>) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />;
}

function SheetClose(props: React.ComponentProps<typeof SheetPrimitive.Close>) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />;
}

function SheetOverlay({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Overlay>) {
  return (
    <SheetPrimitive.Overlay
      data-slot="sheet-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-black/45 backdrop-blur-[2px] data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:duration-(--duration-base) data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:duration-(--duration-slow) motion-reduce:animate-none",
        className,
      )}
      {...props}
    />
  );
}

// Edge sheets fill the height; top and bottom sheets round their inner corners and never cover the
// whole screen, so the page behind still shows.
const sides = {
  top: "inset-x-0 top-0 h-auto max-h-[90dvh] rounded-b-3xl border-b data-[state=closed]:slide-out-to-top data-[state=open]:slide-in-from-top",
  right:
    "inset-y-0 right-0 h-full w-[85%] border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-sm",
  bottom:
    "inset-x-0 bottom-0 h-auto max-h-[90dvh] rounded-t-3xl border-t pb-[env(safe-area-inset-bottom)] data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
  left: "inset-y-0 left-0 h-full w-[85%] border-r data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left sm:max-w-sm",
} as const;

type SheetContentProps = React.ComponentProps<typeof SheetPrimitive.Content> & {
  side?: keyof typeof sides;
  /** Accessible name of the close button. */
  closeLabel: string;
};

function SheetContent({
  className,
  children,
  side = "right",
  closeLabel,
  ...props
}: SheetContentProps) {
  return (
    <SheetPrimitive.Portal>
      <SheetOverlay />
      <SheetPrimitive.Content
        data-slot="sheet-content"
        className={cn(
          // Opens with a long, soft landing; closes quicker, accelerating away.
          "fixed z-50 flex flex-col gap-4 overflow-y-auto bg-background shadow-xl outline-none data-[state=closed]:animate-out data-[state=closed]:duration-(--duration-base) data-[state=closed]:ease-exit data-[state=open]:animate-in data-[state=open]:duration-(--duration-slower) data-[state=open]:ease-emphasized motion-reduce:animate-none",
          sides[side],
          className,
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close className="absolute top-3 right-3 grid size-11 place-items-center rounded-full text-muted-foreground transition-colors outline-none hover:bg-accent hover:text-foreground focus-visible:text-foreground focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none pointer-fine:size-9">
          <XIcon className="size-5" aria-hidden />
          <span className="sr-only">{closeLabel}</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-1.5 p-4", className)}
      {...props}
    />
  );
}

function SheetTitle({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn("font-display text-lg font-semibold tracking-tight text-foreground", className)}
      {...props}
    />
  );
}

function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

export { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger };
