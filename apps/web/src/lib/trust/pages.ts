import type { Route } from "next";

import { type Company, company, missingFacts } from "@/config/company";
import { isDraft, legalDocuments } from "@/content/legal";

/**
 * The trust and legal pages (step 3.8, ADR 0034), every one linked from the footer. A page is
 * kept out of search engines while it still shows a placeholder for a fact the founders haven't
 * given, or while its legal text is a draft.
 */
export const trustPages = {
  about: "/about",
  contact: "/contact",
  pricing: "/pricing",
  tokenProtection: "/token-protection",
  terms: "/terms",
  privacy: "/privacy",
  refunds: "/refund-policy",
  grievances: "/grievances",
} as const satisfies Record<string, Route>;

export type TrustPage = keyof typeof trustPages;

// The company facts each page states.
const FACTS: Record<TrustPage, readonly (keyof Company)[]> = {
  about: ["legalName", "founders"],
  contact: ["legalName", "registeredAddress", "supportPhone", "supportHours", "supportEmail"],
  pricing: [],
  tokenProtection: [],
  terms: ["legalName", "registeredAddress"],
  privacy: ["legalName", "supportEmail"],
  refunds: [],
  grievances: ["grievanceOfficer"],
};

const LEGAL: Partial<Record<TrustPage, keyof typeof legalDocuments>> = {
  terms: "terms",
  privacy: "privacy",
  refunds: "refunds",
};

export function isIndexable(page: TrustPage, facts: Company = company): boolean {
  const missing = new Set(missingFacts(facts));
  const document = LEGAL[page];
  return (
    FACTS[page].every((fact) => !missing.has(fact)) &&
    (document === undefined || !isDraft(legalDocuments[document]))
  );
}

/** The footer's groups, in order. */
export const footerGroups = {
  company: ["about", "contact", "pricing", "tokenProtection"],
  policies: ["terms", "privacy", "refunds", "grievances"],
} as const satisfies Record<string, readonly TrustPage[]>;
