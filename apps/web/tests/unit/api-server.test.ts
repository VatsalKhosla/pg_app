// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { fakeFetch, jsonResponse } from "./api-fakes";

const requestHeaders = new Headers({
  cookie: "session=abc%3D%3D; theme=dark; csrf=t0k3n; =odd; broken",
  "x-request-id": "0192f6d4-page",
});

vi.mock("next/headers", () => ({ headers: () => Promise.resolve(requestHeaders) }));

const { API_COOKIES, forwardedHeaders, getServerApi, pickCookies } =
  await import("@/lib/api/server");

describe("pickCookies", () => {
  it("keeps only the named cookies, exactly as the browser sent them", () => {
    expect(pickCookies(requestHeaders.get("cookie"), ["session", "csrf"])).toBe(
      "session=abc%3D%3D; csrf=t0k3n",
    );
  });

  it("forwards nothing without a cookie header or names", () => {
    expect(pickCookies(null, ["session"])).toBe("");
    expect(pickCookies("session=abc", [])).toBe("");
  });
});

describe("forwardedHeaders", () => {
  it("passes on the API's cookies and the page's request id", () => {
    expect(forwardedHeaders(requestHeaders, ["session"])).toEqual({
      cookie: "session=abc%3D%3D",
      "x-request-id": "0192f6d4-page",
    });
  });
});

describe("getServerApi", () => {
  it("calls the API with the request id and none of the visitor's other cookies", async () => {
    const { fetch, requests } = fakeFetch(() => jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetch);

    const api = await getServerApi();
    await api.GET("/healthz");

    expect(API_COOKIES).toEqual([]);
    expect(requests[0]?.url).toBe("http://127.0.0.1:8000/healthz");
    expect(requests[0]?.headers.get("x-request-id")).toBe("0192f6d4-page");
    expect(requests[0]?.headers.get("cookie")).toBeNull();
  });
});
