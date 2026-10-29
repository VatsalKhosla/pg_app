import { privacy } from "./en-IN/privacy";
import { refunds } from "./en-IN/refunds";
import { terms } from "./en-IN/terms";

/**
 * The legal texts the site shows (step 3.8, ADR 0034), one module per document and locale. Each
 * is a DRAFT until a lawyer has reviewed it; its version then drops the "draft-" prefix, and a
 * production build refuses drafts (src/config/launch.ts). The privacy notice's version is the
 * one people consent to, so it matches the API's PRIVACY_NOTICE_VERSION.
 *
 * Texts use the Markdown subset src/lib/content/markdown.ts reads, with {blanks} filled in when
 * the page renders: the brand, the company's facts and the policies in force, so none of them is
 * written into the text itself.
 */
export interface LegalDocument {
  /** "draft-1" until reviewed, then the reviewed version, e.g. "2027-01". */
  version: string;
  /** When this version was written, YYYY-MM-DD. */
  updated: string;
  text: string;
}

export const legalDocuments = { terms, privacy, refunds } as const;

export type LegalDocumentName = keyof typeof legalDocuments;

export function isDraft(document: Pick<LegalDocument, "version">): boolean {
  return document.version.startsWith("draft");
}
