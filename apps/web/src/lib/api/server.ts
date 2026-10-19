import "server-only";

import type { ApiClient } from "@pg-platform/api-client";
import { headers } from "next/headers";

import { serverEnv } from "@/config/server-env";

import { createWebApiClient } from "./client";

/**
 * Cookies the API owns, forwarded from the visitor's request when the server calls the API on
 * their behalf. Every other cookie stays on the web server. The session and CSRF cookies join this
 * list in step 1.1.
 */
export const API_COOKIES: readonly string[] = [];

/** Server rendering waits at most this long for the API. */
export const SERVER_TIMEOUT_MS = 3_000;

/** The visitor's cookies that the API owns, exactly as the browser sent them. */
export function pickCookies(cookieHeader: string | null, names: readonly string[]): string {
  if (cookieHeader === null || names.length === 0) return "";
  return cookieHeader
    .split(";")
    .map((pair) => pair.trim())
    .filter((pair) => {
      const separator = pair.indexOf("=");
      return separator > 0 && names.includes(pair.slice(0, separator));
    })
    .join("; ");
}

/** Headers for a call made on the visitor's behalf: their API cookies and the request id. */
export function forwardedHeaders(
  requestHeaders: Pick<Headers, "get">,
  cookieNames: readonly string[],
): Record<string, string> {
  const forwarded: Record<string, string> = {};
  const cookie = pickCookies(requestHeaders.get("cookie"), cookieNames);
  if (cookie !== "") forwarded.cookie = cookie;
  // Set by src/proxy.ts, so the API's log lines match this page request.
  const requestId = requestHeaders.get("x-request-id");
  if (requestId !== null) forwarded["x-request-id"] = requestId;
  return forwarded;
}

/** The client for server components and server actions. */
export async function getServerApi(): Promise<ApiClient> {
  return createWebApiClient({
    baseUrl: serverEnv.apiUrl,
    timeoutMs: SERVER_TIMEOUT_MS,
    headers: forwardedHeaders(await headers(), API_COOKIES),
  });
}
