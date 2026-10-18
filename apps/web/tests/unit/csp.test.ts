// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  buildContentSecurityPolicy,
  type CspOptions,
  newNonce,
  reportingEndpoints,
} from "@/lib/security/csp";

const production: CspOptions = {
  nonce: "abc123==",
  isDevelopment: false,
  upgradeInsecureRequests: true,
  connectOrigins: ["https://api.example.test"],
};

function directives(policy: string): Map<string, string[]> {
  return new Map(
    policy.split("; ").map((directive) => {
      const [name = "", ...values] = directive.split(" ");
      return [name, values];
    }),
  );
}

describe("buildContentSecurityPolicy", () => {
  it("runs only scripts that carry the nonce, and what they load", () => {
    const scriptSrc = directives(buildContentSecurityPolicy(production)).get("script-src");

    expect(scriptSrc).toEqual(["'self'", "'nonce-abc123=='", "'strict-dynamic'"]);
  });

  it("allows eval only in development, where React's debugging needs it", () => {
    const policy = directives(buildContentSecurityPolicy({ ...production, isDevelopment: true }));

    expect(policy.get("script-src")).toContain("'unsafe-eval'");
  });

  it("forbids framing, plugins and foreign form targets", () => {
    const policy = directives(buildContentSecurityPolicy(production));

    expect(policy.get("frame-ancestors")).toEqual(["'none'"]);
    expect(policy.get("object-src")).toEqual(["'none'"]);
    expect(policy.get("base-uri")).toEqual(["'self'"]);
    expect(policy.get("form-action")).toEqual(["'self'"]);
  });

  it("keeps images, fonts and connections on known origins", () => {
    const policy = directives(buildContentSecurityPolicy(production));

    expect(policy.get("img-src")).toEqual(["'self'", "data:", "blob:"]);
    expect(policy.get("font-src")).toEqual(["'self'"]);
    expect(policy.get("connect-src")).toEqual(["'self'", "https://api.example.test"]);
  });

  it("upgrades insecure requests only when asked", () => {
    expect(buildContentSecurityPolicy(production)).toContain("upgrade-insecure-requests");
    expect(
      buildContentSecurityPolicy({ ...production, upgradeInsecureRequests: false }),
    ).not.toContain("upgrade-insecure-requests");
  });

  it("reports violations only when there is somewhere to send them", () => {
    const reportUrl = "https://o1.ingest.example.test/api/2/security/?sentry_key=k";
    const policy = directives(buildContentSecurityPolicy({ ...production, reportUrl }));

    expect(policy.get("report-uri")).toEqual([reportUrl]);
    expect(policy.get("report-to")).toEqual(["csp-endpoint"]);
    expect(reportingEndpoints(reportUrl)).toBe(`csp-endpoint="${reportUrl}"`);
    expect(buildContentSecurityPolicy(production)).not.toContain("report-");
  });
});

describe("newNonce", () => {
  it("returns 128 random bits, base64-encoded, different every time", () => {
    const nonces = new Set(Array.from({ length: 1000 }, newNonce));

    expect(nonces.size).toBe(1000);
    for (const nonce of nonces) {
      expect(nonce).toMatch(/^[A-Za-z0-9+/]{22}==$/);
    }
  });
});
