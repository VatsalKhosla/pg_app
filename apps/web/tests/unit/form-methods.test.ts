import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Every form says how it's sent (step 8.1, ZAP's baseline). A form sent before its script has
 * loaded goes the browser's way, and a form without a method goes by GET, putting what was typed,
 * a phone number for one, in the address bar, the browser's history and the host's logs. Forms
 * whose fields belong in the address, like search's filters, say "get" on purpose.
 */
const SRC = path.resolve(__dirname, "../../src");

function tsxFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return tsxFiles(full);
    return entry.name.endsWith(".tsx") ? [full] : [];
  });
}

/** Each `<form …>` opening tag in a file, up to its first ">". */
function formTags(source: string): string[] {
  return [...source.matchAll(/<form(?=[\s>])[^>]*>/gu)].map((match) => match[0]);
}

describe("forms", () => {
  it("each say how they're sent, so nothing typed ends up in an address by accident", () => {
    const without = tsxFiles(SRC).flatMap((file) =>
      formTags(readFileSync(file, "utf8"))
        .filter((tag) => !/\smethod="(post|get)"/u.test(tag))
        .map(() => path.relative(SRC, file)),
    );

    expect(without).toEqual([]);
  });

  it("send by GET only where the fields belong in the address", () => {
    const byGet = tsxFiles(SRC)
      .filter((file) =>
        formTags(readFileSync(file, "utf8")).some((tag) => tag.includes(`method="get"`)),
      )
      .map((file) => path.relative(SRC, file))
      .sort();

    // Filters and searches whose state is the address. Ops' owner and listing searches take an
    // owner's phone, which then lands in the address too (docs/security/asvs-l2.md, 14.2.1).
    expect(byGet).toEqual([
      "app/ops/bookings/page.tsx",
      "app/ops/invoices/page.tsx",
      "app/ops/ledger/page.tsx",
      "app/ops/listings/[id]/beds/page.tsx",
      "app/ops/listings/[id]/pricing/page.tsx",
      "app/ops/listings/page.tsx",
      "app/ops/owners/page.tsx",
      "app/owner/pgs/[id]/calendar/page.tsx",
      "app/owner/pgs/[id]/pricing/page.tsx",
      "components/pg/quote-checker.tsx",
      "components/search/filters.tsx",
    ]);
  });
});
