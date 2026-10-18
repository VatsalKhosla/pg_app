import type { Route } from "next";

/** Ids of the home page sections, shared by the page and the links to them. */
export const homeSections = {
  howItWorks: "how-it-works",
  students: "students",
  owners: "owners",
} as const;

export type NavigationKey = keyof typeof homeSections;

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

// The header and footer link to home page sections until the real pages exist.
export const navigationItems: readonly NavigationItem[] = [
  { key: "howItWorks", href: "/#how-it-works", targetId: homeSections.howItWorks },
  { key: "students", href: "/#students", targetId: homeSections.students },
  { key: "owners", href: "/#owners", targetId: homeSections.owners },
];
