"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

/**
 * The console's sections; the one open is marked for screen readers too. On an area's dusk band
 * (`tone="night"`), the pills are glass and the open one is the sun.
 */
export function OpsNav({
  label,
  links,
  tone = "day",
}: {
  label: string;
  links: readonly { href: Route; label: string; exact?: boolean }[];
  tone?: "day" | "night";
}) {
  const pathname = usePathname();
  const night = tone === "night";
  return (
    <nav
      aria-label={label}
      className={cn(
        "flex flex-wrap items-center gap-1.5 rounded-2xl p-1.5 text-sm",
        night
          ? "bg-night/45 ring-1 ring-white/12 backdrop-blur-md"
          : "border border-border/80 bg-surface/80",
      )}
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
              "inline-flex min-h-9 items-center rounded-xl px-3.5 py-1.5 font-medium transition-colors duration-(--duration-fast) outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
              night
                ? "text-night-foreground hover:bg-white/10"
                : "text-muted-foreground hover:bg-card/60 hover:text-foreground",
              current &&
                (night
                  ? "bg-sun font-semibold text-sun-foreground shadow-sm hover:bg-sun"
                  : "bg-card font-semibold text-foreground shadow-xs ring-1 ring-border/80"),
            )}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
