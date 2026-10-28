import type { Route } from "next";

/** Ids of the home page sections, shared by the page and the links to them. */
export const homeSections = {
  howItWorks: "how-it-works",
  students: "students",
  owners: "owners",
} as const;

export type NavigationKey = "search" | keyof typeof homeSections;

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

// Search first; the rest are home page sections until their real pages exist. A page's target is
// its main content (the layout's #main).
export const navigationItems: readonly NavigationItem[] = [
  { key: "search", href: "/search", targetId: "main" },
  { key: "howItWorks", href: "/#how-it-works", targetId: homeSections.howItWorks },
  { key: "students", href: "/#students", targetId: homeSections.students },
  { key: "owners", href: "/#owners", targetId: homeSections.owners },
];
