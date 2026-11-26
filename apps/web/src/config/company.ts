/**
 * Facts about the company that the trust pages state (step 3.8, ADR 0034): who runs it, how to
 * reach a person, and the grievance officer the Consumer Protection (E-Commerce) Rules, 2020
 * require. They're real-world facts only the founders can give (CLAUDE.md); each stays null, or
 * empty, until they do, and a production build refuses to start while one is missing
 * (src/config/launch.ts).
 *
 * The founders gave theirs on 2026-11-26. The business isn't registered yet, so the registered
 * name and office are still to come: until then the pages say the founders run it, and a
 * production build waits for the registration (with the GSTIN its invoices need).
 *
 * The brand name isn't here: it lives only in brand.ts.
 */

import type { StaticImageData } from "next/image";

export interface Founder {
  name: string;
  /** Their role, e.g. "Co-founder, operations". */
  role: string;
  /** A photo, square, at least 320 px, imported (the web image has no public folder). Without one,
   * their initials stand in. */
  photo?: StaticImageData;
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
  /** The phone numbers a person answers, in E.164. */
  supportPhones: readonly string[];
  /** When it's answered, e.g. "Monday to Saturday, 9 am to 7 pm". */
  supportHours: string | null;
  supportEmail: string | null;
  founders: readonly Founder[];
  grievanceOfficer: GrievanceOfficer | null;
}

export const company: Company = {
  // Not registered yet (the founders, 2026-11-26).
  legalName: null,
  registeredAddress: null,
  // Vatsal's and Suryansh's numbers (2026-11-26).
  supportPhones: ["+919891002696", "+918586891112"],
  supportHours: "every day, 9 am to 9 pm",
  // The founders' Google Workspace address (2026-11-06).
  supportEmail: "support@fixyourstay.in",
  founders: [
    { name: "Vatsal Khosla", role: "Co-founder" },
    { name: "Suryansh Gupta", role: "Co-founder" },
  ],
  grievanceOfficer: {
    name: "Vatsal Khosla",
    designation: "Co-founder",
    email: "support@fixyourstay.in",
    phone: "+919891002696",
  },
};

/** The facts still to come from the founders, by name; empty once every one is in. */
export function missingFacts(facts: Company = company): string[] {
  const missing: string[] = [];
  if (facts.legalName === null) missing.push("legalName");
  if (facts.registeredAddress === null) missing.push("registeredAddress");
  if (facts.supportPhones.length === 0) missing.push("supportPhones");
  if (facts.supportHours === null) missing.push("supportHours");
  if (facts.supportEmail === null) missing.push("supportEmail");
  if (facts.founders.length === 0) missing.push("founders");
  if (facts.grievanceOfficer === null) missing.push("grievanceOfficer");
  return missing;
}
