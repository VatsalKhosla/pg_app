import { cva } from "class-variance-authority";

/*
 * Apart from the Button component, so what every page loads first (the header's menu button, the
 * error pages, the home page's search) can style a plain button without the class merger and the
 * Slot that Button brings: about 12 KB of JavaScript that the first paint doesn't need.
 */
// shadcn/ui's button (new-york style), on the design tokens in globals.css. Sizes give thumbs a
// 44 px target on touch screens and tighten to 40 px (32 px for `sm`) under a mouse, so the owner
// and ops tools stay dense; none goes below 24 px (WCAG 2.2 2.5.8). Pressing gives a slight push,
// and the focus ring is solid with a gap, 3:1 or more against any page colour.
export const buttonVariants = cva(
  [
    "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg text-sm font-semibold whitespace-nowrap select-none",
    "transition-[color,background-color,border-color,box-shadow,transform] duration-(--duration-fast) ease-standard active:scale-[0.98] motion-reduce:transition-none motion-reduce:active:scale-100",
    "outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    "disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  ],
  {
    variants: {
      variant: {
        /** The page's main action. One per view, where possible. */
        default: "bg-primary text-primary-foreground shadow-xs hover:bg-primary-hover",
        /** The marigold fill: the one action that matters most on a screen, such as search. */
        sun: "bg-sun text-sun-foreground shadow-sm hover:bg-sun-hover",
        /** A quieter brand action beside the main one, or a selected filter. */
        soft: "bg-primary-soft text-primary-soft-foreground hover:bg-primary-soft-hover",
        destructive:
          "bg-destructive text-destructive-foreground shadow-xs hover:bg-destructive/90 dark:hover:bg-destructive/85",
        outline:
          "border border-input bg-background text-foreground shadow-xs hover:border-foreground/60 hover:bg-accent dark:bg-transparent",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary-hover",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "font-medium text-primary underline-offset-4 hover:underline active:scale-100",
      },
      size: {
        default:
          "h-11 px-5 has-[>svg]:px-4 pointer-fine:h-10 pointer-fine:px-4 pointer-fine:has-[>svg]:px-3.5",
        sm: "h-9 gap-1.5 px-3.5 has-[>svg]:px-3 pointer-fine:h-8 pointer-fine:px-3 pointer-fine:has-[>svg]:px-2.5",
        lg: "h-12 px-7 text-base has-[>svg]:px-5 [&_svg:not([class*='size-'])]:size-5",
        /** The search capsule's button, as tall as the fields beside it. */
        xl: "h-14 px-7 text-base has-[>svg]:px-6 [&_svg:not([class*='size-'])]:size-5",
        icon: "size-11 pointer-fine:size-10",
        "icon-sm": "size-9 pointer-fine:size-8",
        "icon-lg": "size-12 [&_svg:not([class*='size-'])]:size-5",
      },
      shape: {
        default: "",
        /** Fully rounded: search bars, filter chips and floating actions. */
        pill: "rounded-full",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
      shape: "default",
    },
  },
);
