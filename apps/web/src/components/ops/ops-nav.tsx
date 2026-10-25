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
    <nav aria-label={label} className="flex flex-wrap gap-x-6 gap-y-2 border-b pb-4 text-sm">
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
              "font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline",
              current && "text-foreground underline",
            )}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
