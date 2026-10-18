// @vitest-environment node
import { describe, expect, it } from "vitest";

import { sentryEndpoints } from "@/lib/monitoring/sentry-dsn";

describe("sentryEndpoints", () => {
  it("derives the event origin and the CSP report endpoint from the DSN", () => {
    expect(sentryEndpoints("https://abc123@o99.ingest.example.test/4501", "production")).toEqual({
      origin: "https://o99.ingest.example.test",
      securityReportUrl:
        "https://o99.ingest.example.test/api/4501/security/?sentry_key=abc123&sentry_environment=production",
    });
  });

  it("keeps a self-hosted path prefix and port", () => {
    const { origin, securityReportUrl } = sentryEndpoints(
      "https://key@sentry.example.test:9000/prefix/7",
      "local",
    );

    expect(origin).toBe("https://sentry.example.test:9000");
    expect(securityReportUrl).toBe(
      "https://sentry.example.test:9000/prefix/api/7/security/?sentry_key=key&sentry_environment=local",
    );
  });

  it.each([
    "not a url",
    "https://o1.ingest.example.test/42",
    "https://key@o1.ingest.example.test/",
    "https://key@o1.ingest.example.test/project",
  ])("rejects %s", (dsn) => {
    expect(() => sentryEndpoints(dsn, "local")).toThrow(/NEXT_PUBLIC_SENTRY_DSN/);
  });
});
