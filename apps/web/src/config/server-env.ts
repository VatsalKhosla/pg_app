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
  /** Shared with the API, which signs revalidation requests with it; unset, there are none. */
  revalidateSecret: secret("REVALIDATE_SECRET", process.env.REVALIDATE_SECRET),
} as const;

/** A secret of at least 32 characters, or undefined when unset; anything shorter is a mistake. */
function secret(name: string, value: string | undefined): string | undefined {
  if (value === undefined || value === "") return undefined;
  if (value.length < 32) throw new Error(`${name} must be at least 32 characters`);
  return value;
}
