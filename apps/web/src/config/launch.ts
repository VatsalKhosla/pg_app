import { isDraft, legalDocuments } from "@/content/legal";

import type { AppEnvironment } from "./env";
import { type Company, company, missingFacts } from "./company";

/**
 * What stops a production build (step 3.8, ADR 0034): company facts the founders haven't given
 * yet, and legal texts a lawyer hasn't reviewed. Either would put a placeholder or an unreviewed
 * promise in front of real people. The root layout calls `assertReadyFor` as it loads, so a
 * production build fails while this isn't empty; other environments show the placeholders and
 * the DRAFT notices instead.
 */
export function launchProblems(
  facts: Company = company,
  documents: Record<string, { version: string }> = legalDocuments,
): string[] {
  return [
    ...missingFacts(facts).map((fact) => `src/config/company.ts: ${fact} is still to come`),
    ...Object.entries(documents)
      .filter(([, document]) => isDraft(document))
      .map(([name]) => `src/content/legal: ${name} is a draft that needs a lawyer's review`),
  ];
}

export function assertReadyFor(environment: AppEnvironment): void {
  if (environment !== "production") return;
  const problems = launchProblems();
  if (problems.length > 0) {
    throw new Error(`Not ready for production:\n- ${problems.join("\n- ")}`);
  }
}
