"use client";

import Link from "next/link";
import { type RefObject, useRef } from "react";

import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

import type { NavigationLink } from "./navigation";

export interface MobileNavLabels {
  openMenu: string;
  closeMenu: string;
  menuTitle: string;
  mainNavigation: string;
}

/**
 * The menu sheet itself, loaded on demand by MobileNav. Closing it returns focus to the menu
 * button, unless a link was followed: then focus moves to the section the link lands on, so
 * keyboard and screen reader users continue where they meant to go.
 */
export function MobileNavMenu({
  open,
  onOpenChange,
  labels,
  links,
  returnFocusTo,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  labels: MobileNavLabels;
  links: readonly NavigationLink[];
  returnFocusTo: RefObject<HTMLElement | null>;
}) {
  const followedTarget = useRef<string | null>(null);

  function handleCloseAutoFocus(event: Event) {
    event.preventDefault();
    const targetId = followedTarget.current;
    followedTarget.current = null;
    const section = targetId === null ? null : document.getElementById(targetId);
    (section ?? returnFocusTo.current)?.focus();
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        closeLabel={labels.closeMenu}
        aria-describedby={undefined}
        onCloseAutoFocus={handleCloseAutoFocus}
      >
        <SheetHeader>
          <SheetTitle>{labels.menuTitle}</SheetTitle>
        </SheetHeader>
        <nav aria-label={labels.mainNavigation} className="px-2">
          <ul className="flex flex-col gap-1">
            {links.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="flex min-h-11 items-center rounded-md px-3 text-base font-medium outline-none hover:bg-accent hover:text-accent-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  onClick={() => {
                    followedTarget.current = link.targetId;
                    onOpenChange(false);
                  }}
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </SheetContent>
    </Sheet>
  );
}
