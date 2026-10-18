import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { BrandMark } from "@/components/brand/brand-mark";
import { brand } from "@/config/brand";

import { MobileNav } from "./mobile-nav";
import { type NavigationLink, navigationItems } from "./navigation";

export async function SiteHeader() {
  const t = await getTranslations("Layout");
  const tNavigation = await getTranslations("Navigation");
  const links: NavigationLink[] = navigationItems.map((item) => ({
    href: item.href,
    targetId: item.targetId,
    label: tNavigation(item.key),
  }));

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/80">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        {/* Named by its visible text: the mark beside it is decorative. */}
        <Link
          href="/"
          className="-mx-1 flex items-center gap-2.5 rounded-md px-1 py-1 text-lg font-semibold tracking-tight outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <BrandMark />
          <span>{brand.name}</span>
        </Link>
        <nav aria-label={t("mainNavigation")} className="hidden md:block">
          <ul className="flex items-center gap-1">
            {links.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground outline-none hover:bg-accent hover:text-accent-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <MobileNav
          labels={{
            openMenu: t("openMenu"),
            closeMenu: t("closeMenu"),
            menuTitle: t("menuTitle"),
            mainNavigation: t("mainNavigation"),
          }}
          links={links}
        />
      </div>
    </header>
  );
}
