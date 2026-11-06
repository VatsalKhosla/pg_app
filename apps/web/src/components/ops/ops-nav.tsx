"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

/** The console's sections; the one open is marked for screen readers too. */
export function OpsNav({
  label,
  links,
}: {
  label: string;
  links: readonly { href: Route; label: string; exact?: boolean }[];
}) {
  const pathname = usePathname();
  return (
    <nav
      aria-label={label}
      className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-border/80 bg-surface/80 p-1.5 text-sm"
    >
      {links.map((link) => {
        const current = link.exact
          ? pathname === link.href
          : pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-xl px-3.5 py-1.5 font-medium text-muted-foreground transition-colors hover:bg-card/60 hover:text-foreground",
              current && "bg-card font-semibold text-foreground shadow-xs ring-1 ring-border/80",
            )}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
