import type { Route } from "next";

export type NavigationKey = "search" | "howItWorks" | "students" | "owners";

export interface NavigationItem {
  /** Message key under "Navigation". */
  key: NavigationKey;
  href: Route;
  /** The element the link lands on, which takes focus after a menu link is followed. */
  targetId: string;
}

/** A navigation item with its label translated, ready for a client component. */
export interface NavigationLink {
  href: Route;
  targetId: string;
  label: string;
}

// Search first, then a page each for how it works, for students and parents, and for owners. A
// page's target is its main content (the layout's #main).
export const navigationItems: readonly NavigationItem[] = [
  { key: "search", href: "/search", targetId: "main" },
  { key: "howItWorks", href: "/how-it-works", targetId: "main" },
  { key: "students", href: "/students", targetId: "main" },
  { key: "owners", href: "/owners", targetId: "main" },
];
