import type { Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { BrandMark } from "@/components/brand/brand-mark";
import { Separator } from "@/components/ui/separator";
import { brand } from "@/config/brand";
import { footerGroups, trustPages } from "@/lib/trust/pages";

import { navigationItems } from "./navigation";

const linkClasses =
  "inline-flex min-h-11 items-center rounded-md text-sm text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface motion-reduce:transition-none sm:min-h-8";

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
    <div className="space-y-3">
      <h2 id={id} className="text-xs font-semibold tracking-wider text-foreground uppercase">
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
    <footer className="border-t bg-surface">
      <div className="mx-auto max-w-page space-y-10 px-gutter py-12 sm:py-16">
        <div className="grid gap-10 lg:grid-cols-[1.2fr_2.8fr]">
          <div className="flex items-start gap-3.5">
            <BrandMark className="size-10" />
            <div>
              <p className="font-display text-base font-bold tracking-tight text-foreground">
                {brand.name}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{tBrand("tagline")}</p>
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
        <Separator />
        <p className="text-xs text-muted-foreground">
          {t("copyright", { year: new Date().getFullYear(), brand: brand.name })}
        </p>
      </div>
    </footer>
  );
}
