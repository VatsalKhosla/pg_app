/**
 * Facts about the company that the trust pages state (step 3.8, ADR 0034): who runs it, how to
 * reach a person, and the grievance officer the Consumer Protection (E-Commerce) Rules, 2020
 * require. They're real-world facts only the founders can give (CLAUDE.md), so each stays null,
 * or empty, until they do. Meanwhile the pages show a visible placeholder and keep out of search
 * engines, and a production build refuses to start (src/config/launch.ts).
 *
 * The brand name isn't here: it lives only in brand.ts.
 */

export interface Founder {
  name: string;
  /** Their role, e.g. "Co-founder, operations". */
  role: string;
  /** A photo under /public, e.g. "/founders/name.jpg", square, at least 320 px. */
  photo: string;
}

export interface GrievanceOfficer {
  name: string;
  designation: string;
  email: string;
  /** In E.164, e.g. "+919800000000". */
  phone: string;
}

export interface Company {
  /** The registered name, as on the certificate of incorporation. */
  legalName: string | null;
  /** The registered office's address, in one line. */
  registeredAddress: string | null;
  /** The phone line a person answers, in E.164. */
  supportPhone: string | null;
  /** When it's answered, e.g. "Monday to Saturday, 9 am to 7 pm". */
  supportHours: string | null;
  supportEmail: string | null;
  founders: readonly Founder[];
  grievanceOfficer: GrievanceOfficer | null;
}

export const company: Company = {
  legalName: null,
  registeredAddress: null,
  supportPhone: null,
  supportHours: null,
  supportEmail: null,
  founders: [],
  grievanceOfficer: null,
};

/** The facts still to come from the founders, by name; empty once every one is in. */
export function missingFacts(facts: Company = company): string[] {
  const missing: string[] = [];
  if (facts.legalName === null) missing.push("legalName");
  if (facts.registeredAddress === null) missing.push("registeredAddress");
  if (facts.supportPhone === null) missing.push("supportPhone");
  if (facts.supportHours === null) missing.push("supportHours");
  if (facts.supportEmail === null) missing.push("supportEmail");
  if (facts.founders.length === 0) missing.push("founders");
  if (facts.grievanceOfficer === null) missing.push("grievanceOfficer");
  return missing;
}
