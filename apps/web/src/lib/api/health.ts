import type { ApiClient } from "@pg-platform/api-client";

import { unwrap } from "./client";
import { ApiError } from "./errors";

export type ApiHealth = "online" | "offline";

/** Whether the API answers its liveness probe. Reports failures as "offline" instead of throwing. */
export async function getApiHealth(api: ApiClient): Promise<ApiHealth> {
  try {
    await unwrap(api.GET("/healthz"));
    return "online";
  } catch (error) {
    if (error instanceof ApiError) return "offline";
    throw error;
  }
}
