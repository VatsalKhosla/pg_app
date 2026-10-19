import { publicEnv } from "@/config/env";

import { createWebApiClient } from "./client";

/**
 * The client for client components. The browser sends the visitor's API cookies itself (CORS with
 * credentials; the API allows this site's origin).
 */
export const browserApi = createWebApiClient({
  baseUrl: publicEnv.apiUrl,
  timeoutMs: 10_000,
  credentials: "include",
});
