import { describe, expect, it } from "vitest";

import { type Company, company, missingFacts } from "@/config/company";
import { assertReadyFor, launchProblems } from "@/config/launch";
import { legalDocuments } from "@/content/legal";
import { footerGroups, isIndexable, trustPages } from "@/lib/trust/pages";

// Clearly fictional facts, standing in for the founders' (CLAUDE.md: never invent real ones).
const GIVEN: Company = {
  legalName: "Fictional Stays Private Limited",
  registeredAddress: "1 Fictional Lane, Nowhere 000000",
  supportPhone: "+910000000000",
  supportHours: "Monday to Saturday, 9 am to 7 pm",
  supportEmail: "help@example.com",
  founders: [{ name: "A Fictional Founder", role: "Co-founder", photo: "/founders/a.jpg" }],
  grievanceOfficer: {
    name: "A Fictional Officer",
    designation: "Grievance officer",
    email: "grievances@example.com",
    phone: "+910000000001",
  },
};

describe("the company's facts", () => {
  it("are all still to come from the founders", () => {
    expect(missingFacts(company)).toEqual([
      "legalName",
      "registeredAddress",
      "supportPhone",
      "supportHours",
      "supportEmail",
      "founders",
      "grievanceOfficer",
    ]);
    expect(missingFacts(GIVEN)).toEqual([]);
  });
});

describe("which trust pages search engines may index", () => {
  it("is those with every fact they state, and no draft", () => {
    expect(isIndexable("pricing")).toBe(true);
    expect(isIndexable("tokenProtection")).toBe(true);
    expect(isIndexable("about")).toBe(false);
    expect(isIndexable("grievances")).toBe(false);
    expect(isIndexable("about", GIVEN)).toBe(true);
    expect(isIndexable("contact", GIVEN)).toBe(true);
    // A draft legal text stays out, whatever the facts.
    expect(isIndexable("terms", GIVEN)).toBe(false);
    expect(isIndexable("refunds", GIVEN)).toBe(false);
  });

  it("covers every trust page in the footer", () => {
    expect([...footerGroups.company, ...footerGroups.policies].sort()).toEqual(
      Object.keys(trustPages).sort(),
    );
  });
});

describe("the launch check", () => {
  it("names every missing fact and every draft", () => {
    const problems = launchProblems();
    expect(problems).toHaveLength(7 + Object.keys(legalDocuments).length);
    expect(problems).toContain("src/content/legal: terms is a draft that needs a lawyer's review");
    expect(launchProblems(GIVEN, { terms: { version: "2027-01" } })).toEqual([]);
  });

  it("stops a production build only", () => {
    expect(() => {
      assertReadyFor("production");
    }).toThrow(/Not ready for production/u);
    for (const environment of ["local", "test", "staging"] as const) {
      expect(() => {
        assertReadyFor(environment);
      }).not.toThrow();
    }
  });
});
