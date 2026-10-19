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

  it("sends people without a session from protected pages to sign in, and back after", async () => {
    const { proxy } = await loadProxy();

    function redirectOf(url: string, cookie?: string): string | null {
      const request = new NextRequest(url, {
        headers: cookie === undefined ? {} : { cookie },
      });
      const response = proxy(request);
      return response.status === 307 ? response.headers.get("location") : null;
    }

    expect(redirectOf("http://localhost:3000/account")).toBe(
      "http://localhost:3000/sign-in?next=%2Faccount",
    );
    expect(redirectOf("http://localhost:3000/account/sessions?tab=all")).toBe(
      "http://localhost:3000/sign-in?next=%2Faccount%2Fsessions%3Ftab%3Dall",
    );
    expect(redirectOf("http://localhost:3000/staff")).toBe(
      "http://localhost:3000/staff/sign-in?next=%2Fstaff",
    );
    // Sign-in pages, other pages, and anyone with a session cookie go through.
    expect(redirectOf("http://localhost:3000/staff/sign-in")).toBeNull();
    expect(redirectOf("http://localhost:3000/accounting")).toBeNull();
    expect(redirectOf("http://localhost:3000/account", "__Secure-session=token")).toBeNull();
  });

  it("lets Turnstile's challenge frame in only when a site key is set", async () => {
    const without = (await loadProxy()).proxy(new NextRequest("http://localhost:3000/"));
    vi.stubEnv("NEXT_PUBLIC_TURNSTILE_SITE_KEY", "1x00000000000000000000AA");
    const withKey = (await loadProxy()).proxy(new NextRequest("http://localhost:3000/"));

    expect(without.headers.get("content-security-policy")).toContain("frame-src 'none';");
    expect(withKey.headers.get("content-security-policy")).toContain(
      "frame-src https://challenges.cloudflare.com;",
    );
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
