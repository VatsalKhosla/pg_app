import type { Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { BrandMark } from "@/components/brand/brand-mark";
import { buttonVariants } from "@/components/ui/button";
import { brand } from "@/config/brand";
import { ACCOUNT_PATH, SIGN_IN_PATH, STAFF_HOME_PATH } from "@/lib/auth/routes";
import { getSessionForHeader, isStaff } from "@/lib/auth/session";

import { MobileNav } from "./mobile-nav";
import { type NavigationLink, navigationItems } from "./navigation";

export async function SiteHeader() {
  const t = await getTranslations("Layout");
  const tNavigation = await getTranslations("Navigation");
  const tHeader = await getTranslations("Header");
  const me = await getSessionForHeader();
  const accountLink: { href: Route; label: string } =
    me === null
      ? { href: SIGN_IN_PATH, label: tHeader("signIn") }
      : isStaff(me)
        ? { href: STAFF_HOME_PATH, label: tHeader("staffTools") }
        : { href: ACCOUNT_PATH, label: tHeader("account") };
  const links: NavigationLink[] = navigationItems.map((item) => ({
    href: item.href,
    targetId: item.targetId,
    label: tNavigation(item.key),
  }));

  return (
    <header className="sticky top-0 z-40 border-b border-border/80 bg-background/90 backdrop-blur-md supports-backdrop-filter:bg-background/75">
      <div className="mx-auto flex h-16 max-w-page items-center justify-between gap-4 px-gutter sm:h-18">
        {/* Named by its visible text: the mark beside it is decorative. */}
        <Link
          href="/"
          className="-mx-1.5 flex items-center gap-2.5 rounded-xl px-1.5 py-1 font-display text-lg font-bold tracking-tight text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
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
                  className="inline-flex min-h-10 items-center rounded-full px-3.5 text-sm font-medium text-muted-foreground transition-colors outline-none hover:bg-secondary hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex items-center gap-1.5">
          <Link
            href={accountLink.href}
            className={buttonVariants({
              variant: me === null ? "default" : "outline",
              size: "sm",
              shape: "pill",
            })}
          >
            {accountLink.label}
          </Link>
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
      </div>
    </header>
  );
}
