import type { Metadata } from "next";

import { isIndexable, type TrustPage, trustPages } from "./pages";

/** A trust page's metadata: kept out of search engines while it shows a placeholder or a draft. */
export function trustMetadata(page: TrustPage, title: string, description: string): Metadata {
  const path = trustPages[page];
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { title, description, url: path, type: "website" },
    robots: isIndexable(page) ? undefined : { index: false, follow: true },
  };
}
