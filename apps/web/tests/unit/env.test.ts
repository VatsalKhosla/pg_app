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
    expect(env.apiUrl.origin).toBe("http://localhost:8000");
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

async function loadParser() {
  vi.resetModules();
  return import("@/config/env");
}

describe("parseMapTiles", () => {
  it("uses OpenStreetMap's servers for local development only", async () => {
    const { OSM_TILES, parseMapTiles } = await loadParser();

    expect(parseMapTiles(undefined, undefined, "local")).toBe(OSM_TILES);
    expect(OSM_TILES.attribution).toContain("OpenStreetMap");
    for (const environment of ["test", "staging", "production"] as const) {
      expect(parseMapTiles(undefined, undefined, environment)).toBeUndefined();
    }
  });

  it("takes a provider's https template with the credit its terms ask for, as text", async () => {
    const { parseMapTiles } = await loadParser();

    expect(
      parseMapTiles("https://tiles.example.test/{z}/{x}/{y}.png", "© Example <Maps>", "production"),
    ).toEqual({
      url: "https://tiles.example.test/{z}/{x}/{y}.png",
      attribution: "© Example &#60;Maps&#62;",
    });
  });

  it("refuses tiles without their credit, or a template that isn't one", async () => {
    const { parseMapTiles } = await loadParser();

    expect(() =>
      parseMapTiles("https://tiles.example.test/{z}/{x}/{y}.png", undefined, "production"),
    ).toThrow(/ATTRIBUTION/);
    expect(() =>
      parseMapTiles("http://tiles.example.test/{z}/{x}/{y}.png", "©", "production"),
    ).toThrow(/https/);
    expect(() => parseMapTiles("https://tiles.example.test/tile.png", "©", "production")).toThrow(
      /\{z\}/,
    );
  });
});
