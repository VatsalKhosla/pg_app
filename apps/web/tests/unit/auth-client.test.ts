// @vitest-environment-options {"url": "https://www.example.test/"}
// A secure page: browsers (and jsdom) keep __Secure- cookies only when set Secure from one.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeFetch, jsonResponse, problemResponse } from "./api-fakes";

const challenge = { challengeId: "c1", expiresAt: "x", resendAfter: "y" };

function setCookies(cookie: string) {
  for (const pair of document.cookie.split(";")) {
    const name = pair.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; Max-Age=0; Path=/; Secure`;
  }
  if (cookie !== "") document.cookie = `${cookie}; Path=/; Secure`;
}

/** The auth client with `respond` as the network; browserApi takes fetch when first loaded. */
async function clientWith(respond: (request: Request) => Response) {
  const fake = fakeFetch(respond);
  vi.resetModules();
  vi.stubGlobal("fetch", fake.fetch);
  return { client: await import("@/lib/auth/client"), requests: fake.requests };
}

beforeEach(() => {
  setCookies("");
});

afterEach(() => {
  setCookies("");
});

describe("the auth client", () => {
  it("sends the CSRF token from its cookie with a state-changing call", async () => {
    setCookies("__Secure-csrf=token-from-cookie");
    const { client, requests } = await clientWith(() => jsonResponse(challenge, { status: 202 }));

    await client.requestCode("98765 43210", "turnstile-token");

    expect(requests).toHaveLength(1);
    expect(requests[0]?.headers.get("x-csrf-token")).toBe("token-from-cookie");
    expect(await requests[0]?.json()).toEqual({
      phone: "98765 43210",
      humanCheckToken: "turnstile-token",
    });
  });

  it("asks the API for a token when there is no cookie yet", async () => {
    const { client, requests } = await clientWith((request) =>
      request.url.endsWith("/v1/auth/csrf")
        ? jsonResponse({ csrfToken: "fresh-token" })
        : jsonResponse(challenge, { status: 202 }),
    );

    await client.requestCode("98765 43210", "t");

    expect(requests.map((request) => new URL(request.url).pathname)).toEqual([
      "/v1/auth/csrf",
      "/v1/auth/otp/request",
    ]);
    expect(requests[1]?.headers.get("x-csrf-token")).toBe("fresh-token");
  });

  it("tries once more with a new token when the old one no longer matches the session", async () => {
    setCookies("__Secure-csrf=stale-token");
    let tries = 0;
    const { client, requests } = await clientWith((request) => {
      if (request.url.endsWith("/v1/auth/csrf")) return jsonResponse({ csrfToken: "fresh-token" });
      tries += 1;
      return tries === 1
        ? problemResponse(403, { title: "Forbidden", code: "CSRF_TOKEN_INVALID" })
        : new Response(null, { status: 204 });
    });

    await client.signOut();

    expect(requests.map((request) => request.headers.get("x-csrf-token"))).toEqual([
      "stale-token",
      null,
      "fresh-token",
    ]);
  });

  it("doesn't try again for any other refusal", async () => {
    setCookies("__Secure-csrf=token");
    const { client, requests } = await clientWith(() =>
      problemResponse(400, { title: "Bad code", code: "OTP_INVALID" }),
    );

    await expect(client.verifyCode("c1", "123456")).rejects.toMatchObject({ code: "OTP_INVALID" });
    expect(requests).toHaveLength(1);
  });
});
