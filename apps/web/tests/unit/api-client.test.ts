// @vitest-environment node
import { describe, expect, it } from "vitest";

import { createWebApiClient, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getApiHealth } from "@/lib/api/health";

import { fakeFetch, hangingFetch, jsonResponse, problemResponse } from "./api-fakes";

function client(fetch: typeof globalThis.fetch, timeoutMs = 1_000) {
  return createWebApiClient({
    baseUrl: "http://api.test/",
    timeoutMs,
    headers: { "x-request-id": "page-request" },
    fetch,
  });
}

describe("createWebApiClient", () => {
  it("calls the API's paths with the configured headers and no caching", async () => {
    const { fetch, requests } = fakeFetch(() => jsonResponse({ status: "ok" }));

    const health = await unwrap(client(fetch).GET("/healthz"));

    expect(health).toEqual({ status: "ok" });
    expect(requests.map((request) => request.url)).toEqual(["http://api.test/healthz"]);
    expect(requests[0]?.headers.get("x-request-id")).toBe("page-request");
    expect(requests[0]?.cache).toBe("no-store");
  });

  it("turns problem details into an ApiError", async () => {
    const { fetch } = fakeFetch(() =>
      problemResponse(503, { title: "Service unavailable", code: "SERVICE_UNAVAILABLE" }),
    );

    const error = await unwrap(client(fetch).GET("/healthz")).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 503,
      code: "SERVICE_UNAVAILABLE",
      requestId: "req-from-header",
    });
  });

  it("treats an error response with an empty body as an error", async () => {
    const { fetch } = fakeFetch(
      () => new Response(null, { status: 500, headers: { "content-length": "0" } }),
    );

    await expect(unwrap(client(fetch).GET("/healthz"))).rejects.toMatchObject({
      status: 500,
      code: "UNEXPECTED_RESPONSE",
    });
  });

  it("gives up on a slow API", async () => {
    const { fetch } = hangingFetch();

    await expect(unwrap(client(fetch, 20).GET("/healthz"))).rejects.toMatchObject({
      code: "API_TIMEOUT",
    });
  });

  it("reports a network failure as an unreachable API", async () => {
    const failing = () => Promise.reject(new TypeError("fetch failed"));

    await expect(unwrap(client(failing).GET("/healthz"))).rejects.toMatchObject({
      code: "API_UNREACHABLE",
    });
  });

  it("passes a caller's cancellation through instead of calling it an API failure", async () => {
    const controller = new AbortController();
    const { fetch } = hangingFetch();

    const call = unwrap(client(fetch).GET("/healthz", { signal: controller.signal }));
    controller.abort();

    await expect(call).rejects.toMatchObject({ name: "AbortError" });
    await expect(call).rejects.not.toBeInstanceOf(ApiError);
  });
});

describe("getApiHealth", () => {
  it("is online when the liveness probe answers", async () => {
    const { fetch } = fakeFetch(() => jsonResponse({ status: "ok" }));

    expect(await getApiHealth(client(fetch))).toBe("online");
  });

  it("is offline when the API fails or can't be reached", async () => {
    const { fetch } = fakeFetch(() =>
      problemResponse(500, { title: "Internal server error", code: "INTERNAL_ERROR" }),
    );
    const unreachable = () => Promise.reject(new TypeError("fetch failed"));

    expect(await getApiHealth(client(fetch))).toBe("offline");
    expect(await getApiHealth(client(unreachable))).toBe("offline");
  });
});
