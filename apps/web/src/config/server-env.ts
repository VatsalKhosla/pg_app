import "server-only";

import { parseUrl, publicEnv } from "./env";

/**
 * Configuration only the web server sees, read when it starts (never inlined into the browser
 * bundle), so one build can run anywhere.
 */
export const serverEnv = {
  /** Where the server reaches the API: an internal address in production, else the public URL. */
  apiUrl:
    process.env.API_URL === undefined || process.env.API_URL === ""
      ? publicEnv.apiUrl
      : parseUrl("API_URL", process.env.API_URL, ""),
} as const;
