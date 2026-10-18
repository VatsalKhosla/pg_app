// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

async function loadEnv() {
  vi.resetModules();
  const { publicEnv } = await import("@/config/env");
  return publicEnv;
}

describe("publicEnv", () => {
  it("defaults to a local setup with error reporting off", async () => {
    for (const name of [
      "NEXT_PUBLIC_APP_ENV",
      "NEXT_PUBLIC_SITE_URL",
      "NEXT_PUBLIC_API_URL",
      "NEXT_PUBLIC_SENTRY_DSN",
    ]) {
      vi.stubEnv(name, "");
    }

    const env = await loadEnv();

    expect(env.appEnv).toBe("local");
    expect(env.siteUrl.href).toBe("http://localhost:3000/");
    expect(env.apiUrl.origin).toBe("http://127.0.0.1:8000");
    expect(env.sentryDsn).toBeUndefined();
  });

  it("reads what is configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://www.example.test");
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://key@o1.ingest.example.test/2");

    const env = await loadEnv();

    expect(env.appEnv).toBe("production");
    expect(env.siteUrl.origin).toBe("https://www.example.test");
    expect(env.sentryDsn).toBe("https://key@o1.ingest.example.test/2");
  });

  it("fails fast on an unknown environment or a malformed URL", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "prod");
    await expect(loadEnv()).rejects.toThrow(/NEXT_PUBLIC_APP_ENV/);

    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "api.example.test");
    await expect(loadEnv()).rejects.toThrow(/NEXT_PUBLIC_API_URL/);
  });
});
