import type { MetadataRoute } from "next";
import { getTranslations } from "next-intl/server";

import { brand } from "@/config/brand";
import { defaultLocale } from "@/i18n/config";

// The web app manifest, so the site can be installed as an app (the service worker comes with
// step 3.9). The icons are the ones src/app/icon.tsx generates.
export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const t = await getTranslations({ locale: defaultLocale, namespace: "Metadata" });

  return {
    id: "/",
    name: brand.name,
    short_name: brand.name,
    description: t("description"),
    lang: defaultLocale,
    dir: "ltr",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: brand.surfaces.light,
    theme_color: brand.surfaces.light,
    icons: [
      { src: "/icon/192", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon/512", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon/512", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
