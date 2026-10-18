// @vitest-environment node
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

async function loadProxy() {
  vi.resetModules();
  return import("@/proxy");
}

function nonceOf(policy: string | null): string | undefined {
  return /'nonce-([^']+)'/.exec(policy ?? "")?.[1];
}

describe("proxy", () => {
  it("gives the page and the browser the same policy, with a fresh nonce", async () => {
    const { proxy } = await loadProxy();

    const response = proxy(new NextRequest("http://localhost:3000/"));
    const policy = response.headers.get("content-security-policy");
    const nonce = nonceOf(policy);

    expect(nonce).toBeDefined();
    // NextResponse.next({ request }) passes request headers on to the page as x-middleware-request-*.
    expect(response.headers.get("x-middleware-request-x-nonce")).toBe(nonce);
    expect(response.headers.get("x-middleware-request-content-security-policy")).toBe(policy);
    const next = proxy(new NextRequest("http://localhost:3000/"));
    expect(nonceOf(next.headers.get("content-security-policy"))).not.toBe(nonce);
  });

  it("lets the browser call the API", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.test");
    const { proxy } = await loadProxy();

    const policy = proxy(new NextRequest("http://localhost:3000/")).headers.get(
      "content-security-policy",
    );

    expect(policy).toContain("connect-src 'self' https://api.example.test;");
    expect(policy).not.toContain("report-uri");
  });

  it("sends Sentry's origin and violation reports there when error reporting is on", async () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://publickey@o1.ingest.example.test/42");
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "staging");
    const { proxy } = await loadProxy();

    const response = proxy(new NextRequest("https://www.example.test/"));
    const policy = response.headers.get("content-security-policy") ?? "";
    const reportUrl =
      "https://o1.ingest.example.test/api/42/security/?sentry_key=publickey&sentry_environment=staging";

    expect(policy).toContain("https://o1.ingest.example.test;");
    expect(policy).toContain(`report-uri ${reportUrl}; report-to csp-endpoint`);
    expect(response.headers.get("reporting-endpoints")).toBe(`csp-endpoint="${reportUrl}"`);
  });

  it("runs for pages but not for static files, icons, the manifest or prefetches", async () => {
    const { config } = await loadProxy();

    for (const url of ["/", "/pg/some-pg", "/icons-guide", "/robots.txt.bak"]) {
      expect(unstable_doesMiddlewareMatch({ config, url }), url).toBe(true);
    }
    for (const url of [
      "/_next/static/chunks/main.js",
      "/_next/image?url=x",
      "/favicon.ico",
      "/icon/192",
      "/apple-icon",
      "/manifest.webmanifest",
      "/robots.txt",
    ]) {
      expect(unstable_doesMiddlewareMatch({ config, url }), url).toBe(false);
    }
    expect(
      unstable_doesMiddlewareMatch({ config, url: "/", headers: { "next-router-prefetch": "1" } }),
    ).toBe(false);
  });
});
