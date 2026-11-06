import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The look every text-like control shares (Input here, Select and Textarea in fields.tsx). The
 * border keeps 3:1 against the page (WCAG 1.4.11) and darkens under the pointer; focus thickens it
 * to a 2 px line in the focus colour, the way the best booking sites do. 16 px text on phones, so
 * iOS doesn't zoom in on focus.
 */
export const controlClasses = cn(
  "w-full min-w-0 rounded-lg border border-input bg-background px-3.5 text-base text-foreground shadow-xs outline-none md:text-sm",
  "transition-[color,border-color,box-shadow] duration-(--duration-fast) ease-standard motion-reduce:transition-none",
  "placeholder:text-muted-foreground hover:border-foreground/60 dark:bg-white/[0.03]",
  "focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring focus-visible:hover:border-ring",
  // Invalid: a red line, which thickens on focus like any other.
  "aria-invalid:border-destructive aria-invalid:hover:border-destructive aria-invalid:focus-visible:border-destructive aria-invalid:focus-visible:ring-destructive",
  "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-input",
);

// shadcn/ui's input (new-york style): 44 px tall on touch screens, 40 px under a mouse.
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        controlClasses,
        "flex h-11 py-1 pointer-fine:h-10",
        "file:mr-3 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
