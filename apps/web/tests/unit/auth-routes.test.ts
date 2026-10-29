// @vitest-environment node
import { describe, expect, it } from "vitest";

import { safeNext, signInPageFor, signInUrl } from "@/lib/auth/routes";

describe("safeNext", () => {
  it("keeps paths on this site, with their query and fragment", () => {
    expect(safeNext("/account", "/")).toBe("/account");
    expect(safeNext("/search?near=north-campus#map", "/")).toBe("/search?near=north-campus#map");
  });

  it.each([
    ["another site", "https://evil.example/"],
    ["a protocol-relative URL", "//evil.example/"],
    ["a backslash trick", "/\\evil.example"],
    ["a javascript: URL", "javascript:alert(1)"],
    ["a relative path", "account"],
    ["whitespace", "/account two"],
    ["a control character", "/account\n"],
    ["a sign-in page", "/sign-in?next=/account"],
    ["the staff sign-in page", "/staff/sign-in"],
    ["nothing", undefined],
    ["several values", ["/a", "/b"]],
    ["a very long value", `/${"a".repeat(600)}`],
  ])("falls back for %s", (_, value) => {
    expect(safeNext(value, "/account")).toBe("/account");
  });
});

describe("signInPageFor", () => {
  it("names the sign-in page of each protected area", () => {
    expect(signInPageFor("/account")).toBe("/sign-in");
    expect(signInPageFor("/account/sessions")).toBe("/sign-in");
    expect(signInPageFor("/staff")).toBe("/staff/sign-in");
    expect(signInPageFor("/staff/data-requests")).toBe("/staff/sign-in");
    expect(signInPageFor("/owner")).toBe("/sign-in");
    expect(signInPageFor("/owner/agreement")).toBe("/sign-in");
    expect(signInPageFor("/admin/policies")).toBe("/staff/sign-in");
    expect(signInPageFor("/administration")).toBeUndefined();
  });

  it("leaves sign-in pages and everything else alone", () => {
    expect(signInPageFor("/sign-in")).toBeUndefined();
    expect(signInPageFor("/staff/sign-in")).toBeUndefined();
    expect(signInPageFor("/")).toBeUndefined();
    expect(signInPageFor("/accounting")).toBeUndefined();
    expect(signInPageFor("/owners-guide")).toBeUndefined();
  });
});

describe("signInUrl", () => {
  it("carries where to go next, encoded", () => {
    expect(signInUrl("/sign-in", "/account?tab=all")).toBe("/sign-in?next=%2Faccount%3Ftab%3Dall");
  });
});
