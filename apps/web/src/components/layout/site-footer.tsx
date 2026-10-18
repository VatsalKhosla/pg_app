import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { BrandMark } from "@/components/brand/brand-mark";
import { brand } from "@/config/brand";

import { navigationItems } from "./navigation";

export async function SiteFooter() {
  const t = await getTranslations("Layout");
  const tBrand = await getTranslations("Brand");
  const tNavigation = await getTranslations("Navigation");

  return (
    <footer className="border-t bg-muted/40">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <BrandMark className="size-9" />
          <div>
            <p className="font-semibold">{brand.name}</p>
            <p className="text-sm text-muted-foreground">{tBrand("tagline")}</p>
          </div>
        </div>
        <nav aria-label={t("footerNavigation")}>
          <ul className="flex flex-col gap-1 sm:flex-row sm:gap-2">
            {navigationItems.map((item) => (
              <li key={item.key}>
                <Link
                  href={item.href}
                  className="inline-flex min-h-11 items-center rounded-md px-2 text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:min-h-0 sm:py-1"
                >
                  {tNavigation(item.key)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}
