"use client";

import { MenuIcon } from "lucide-react";
import { lazy, Suspense, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

import type { MobileNavLabels } from "./mobile-nav-menu";
import type { NavigationLink } from "./navigation";

// The menu (a Radix dialog) loads the first time someone reaches for the button, not with the
// page: most visitors never open it, and the page's JavaScript budget is tight (ARCHITECTURE §16).
const loadMenu = () => import("./mobile-nav-menu");
const MobileNavMenu = lazy(() => loadMenu().then((module) => ({ default: module.MobileNavMenu })));

/**
 * The menu button on small screens. Labels arrive translated from the server, so the browser
 * needs no message formatter for them.
 */
export function MobileNav({
  labels,
  links,
}: {
  labels: MobileNavLabels;
  links: readonly NavigationLink[];
}) {
  const [open, setOpen] = useState(false);
  const [requested, setRequested] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  function preload() {
    void loadMenu();
  }

  return (
    <>
      <Button
        ref={buttonRef}
        variant="ghost"
        size="icon-lg"
        className="md:hidden"
        aria-label={labels.openMenu}
        aria-haspopup="dialog"
        aria-expanded={open}
        onPointerEnter={preload}
        onPointerDown={preload}
        onFocus={preload}
        onClick={() => {
          setRequested(true);
          setOpen(true);
        }}
      >
        <MenuIcon className="size-6" aria-hidden />
      </Button>
      {requested ? (
        <Suspense fallback={null}>
          <MobileNavMenu
            open={open}
            onOpenChange={setOpen}
            labels={labels}
            links={links}
            returnFocusTo={buttonRef}
          />
        </Suspense>
      ) : null}
    </>
  );
}
