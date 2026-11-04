import { publicEnv } from "@/config/env";

import { createWebApiClient } from "./client";

/**
 * The client for client components. The browser sends the visitor's API cookies itself (CORS with
 * credentials, as the API allows this site's origin; or simply same-origin, on a site that serves
 * the API itself).
 */
export const browserApi = createWebApiClient({
  baseUrl: publicEnv.browserApiOrigin,
  timeoutMs: publicEnv.apiWaitMs ?? 10_000,
  credentials: "include",
});
