import { headers } from "next/headers";

import { jsonLdText, type Thing } from "@/lib/seo/json-ld";

/**
 * Structured data for search engines, in a <script type="application/ld+json">. It isn't run,
 * but it carries the request's nonce like every other script (ADR 0011), and its text can't
 * close the element (jsonLdText).
 */
export async function JsonLd({ data }: { data: Thing | Thing[] }) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <script
      type="application/ld+json"
      nonce={nonce}
      // Not HTML: JSON, with every "<" escaped.
      dangerouslySetInnerHTML={{ __html: jsonLdText(data) }}
    />
  );
}
