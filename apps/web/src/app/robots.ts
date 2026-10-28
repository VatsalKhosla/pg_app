import type { MetadataRoute } from "next";

import { publicEnv } from "@/config/env";

// Staging is closed to crawlers; everywhere else the site is open, and says where its sitemap
// is. Private areas (owner, ops and account pages) are kept out of search with noindex instead,
// which crawlers can only see if they may fetch the page.
export default function robots(): MetadataRoute.Robots {
  if (publicEnv.appEnv === "staging") {
    return { rules: { userAgent: "*", disallow: "/" } };
  }
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: new URL("/sitemap.xml", publicEnv.siteUrl).toString(),
  };
}
