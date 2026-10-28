// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isSignedByTheApi,
  MAX_AGE_SECONDS,
  revalidationBody,
  signature,
} from "@/lib/security/revalidation";

// The API signs as apps/api/src/app/core/web_cache.py does; this vector was worked out there.
const SECRET = "a-revalidation-secret-of-32-chars!!";
const TIMESTAMP = "1815559200";
const BODY = '{"tags":["listing:asha-pg-kamla-nagar","listings"]}';
const SIGNED = "fb58a32915b0573b2bded0dcf1eb98d7d8bca163cfc85ba07312329eb54e2a72";
const NOW_MS = Number(TIMESTAMP) * 1_000;

function check(overrides: Partial<Parameters<typeof isSignedByTheApi>[0]> = {}): boolean {
  return isSignedByTheApi({
    secret: SECRET,
    timestamp: TIMESTAMP,
    signed: SIGNED,
    body: BODY,
    nowMs: NOW_MS,
    ...overrides,
  });
}

describe("revalidation requests", () => {
  it("are signed the way the API signs them", () => {
    expect(signature(SECRET, TIMESTAMP, BODY)).toBe(SIGNED);
    expect(check()).toBe(true);
  });

  it("are the API's only within five minutes of being sent", () => {
    expect(check({ nowMs: NOW_MS + MAX_AGE_SECONDS * 1_000 })).toBe(true);
    expect(check({ nowMs: NOW_MS + (MAX_AGE_SECONDS + 1) * 1_000 })).toBe(false);
    expect(check({ nowMs: NOW_MS - (MAX_AGE_SECONDS + 1) * 1_000 })).toBe(false);
  });

  it.each([
    ["another secret", { secret: "another-secret-of-thirty-two-chars!!" }],
    ["another body", { body: '{"tags":["listings"]}' }],
    ["another time", { timestamp: "1815559201" }],
    ["no time", { timestamp: null }],
    ["no signature", { signed: null }],
    ["a signature that isn't hex", { signed: "z".repeat(64) }],
    ["a short signature", { signed: SIGNED.slice(0, 32) }],
    ["a time that isn't a number", { timestamp: "soon" }],
  ])("aren't the API's with %s", (_, overrides) => {
    expect(check(overrides)).toBe(false);
  });

  it("name only tags the web app keeps", () => {
    expect(revalidationBody.safeParse(JSON.parse(BODY)).success).toBe(true);
    for (const body of [
      { tags: ["reference"] },
      { tags: ["listing:Not A Slug"] },
      { tags: [] },
      { tags: ["listings"], more: true },
      { tags: Array.from({ length: 21 }, () => "listings") },
    ]) {
      expect(revalidationBody.safeParse(body).success).toBe(false);
    }
  });
});

describe("POST /api/revalidate", () => {
  afterEach(() => {
    vi.doUnmock("next/cache");
  });

  async function route(secret: string | undefined) {
    vi.resetModules();
    vi.stubEnv("REVALIDATE_SECRET", secret ?? "");
    const revalidateTag = vi.fn();
    vi.doMock("next/cache", () => ({ revalidateTag }));
    vi.spyOn(Date, "now").mockReturnValue(NOW_MS);
    const { POST } = await import("@/app/api/revalidate/route");
    return { POST, revalidateTag };
  }

  function request(body: string, headers: Record<string, string>) {
    return new Request("http://localhost:3000/api/revalidate", {
      method: "POST",
      body,
      headers: { "content-type": "application/json", ...headers },
    }) as unknown as Parameters<Awaited<ReturnType<typeof route>>["POST"]>[0];
  }

  const signedHeaders = { "x-revalidate-timestamp": TIMESTAMP, "x-revalidate-signature": SIGNED };

  it("isn't there without the shared secret", async () => {
    const { POST, revalidateTag } = await route(undefined);

    expect((await POST(request(BODY, signedHeaders))).status).toBe(404);
    expect(revalidateTag).not.toHaveBeenCalled();
  });

  it("refuses a request the API didn't sign", async () => {
    const { POST, revalidateTag } = await route(SECRET);

    const response = await POST(
      request(BODY, { ...signedHeaders, "x-revalidate-signature": "0".repeat(64) }),
    );

    expect(response.status).toBe(401);
    expect(revalidateTag).not.toHaveBeenCalled();
  });

  it("drops the named data at once", async () => {
    const { POST, revalidateTag } = await route(SECRET);

    const response = await POST(request(BODY, signedHeaders));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      revalidated: ["listing:asha-pg-kamla-nagar", "listings"],
    });
    expect(revalidateTag.mock.calls).toEqual([
      ["listing:asha-pg-kamla-nagar", { expire: 0 }],
      ["listings", { expire: 0 }],
    ]);
  });
});
