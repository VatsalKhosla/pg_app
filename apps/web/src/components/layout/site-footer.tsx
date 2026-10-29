import type { Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { BrandMark } from "@/components/brand/brand-mark";
import { brand } from "@/config/brand";
import { footerGroups, trustPages } from "@/lib/trust/pages";

import { navigationItems } from "./navigation";

const linkClasses =
  "inline-flex min-h-11 items-center rounded-md text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:min-h-0 sm:py-1";

function FooterGroup({
  id,
  title,
  links,
}: {
  id: string;
  title: string;
  links: readonly { href: Route; label: string }[];
}) {
  return (
    <div className="space-y-2">
      <h2 id={id} className="text-sm font-semibold">
        {title}
      </h2>
      <ul aria-labelledby={id} className="space-y-1">
        {links.map((link) => (
          <li key={link.label}>
            <Link href={link.href} className={linkClasses}>
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Every page's footer: the main sections, and the trust and legal pages (step 3.8), every one of
 * them linked here.
 */
export async function SiteFooter() {
  const [t, tBrand, tNavigation, tTrust] = await Promise.all([
    getTranslations("Layout"),
    getTranslations("Brand"),
    getTranslations("Navigation"),
    getTranslations("Trust"),
  ]);
  const trustLinks = (pages: readonly (keyof typeof trustPages)[]) =>
    pages.map((page) => ({ href: trustPages[page], label: tTrust(`pages.${page}`) }));

  return (
    <footer className="border-t bg-muted/40">
      <div className="mx-auto max-w-6xl space-y-8 px-4 py-10 sm:px-6">
        <div className="grid gap-8 lg:grid-cols-[1fr_3fr]">
          <div className="flex items-start gap-3">
            <BrandMark className="size-9" />
            <div>
              <p className="font-semibold">{brand.name}</p>
              <p className="text-sm text-muted-foreground">{tBrand("tagline")}</p>
            </div>
          </div>
          <nav aria-label={t("footerNavigation")} className="grid gap-8 sm:grid-cols-3">
            <FooterGroup
              id="footer-explore"
              title={t("footerExplore")}
              links={navigationItems.map((item) => ({
                href: item.href,
                label: tNavigation(item.key),
              }))}
            />
            <FooterGroup
              id="footer-company"
              title={t("footerCompany")}
              links={trustLinks(footerGroups.company)}
            />
            <FooterGroup
              id="footer-policies"
              title={t("footerPolicies")}
              links={trustLinks(footerGroups.policies)}
            />
          </nav>
        </div>
        <p className="text-sm text-muted-foreground">
          {t("copyright", { year: new Date().getFullYear(), brand: brand.name })}
        </p>
      </div>
    </footer>
  );
}
