import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { CSRF_COOKIE } from "@/lib/auth/routes";

/**
 * The CSRF token every state-changing call from the browser carries (ADR 0014): read from its
 * cookie, or fetched when there isn't one yet.
 */
function cookieValue(name: string): string | undefined {
  for (const pair of document.cookie.split(";")) {
    const separator = pair.indexOf("=");
    if (separator > 0 && pair.slice(0, separator).trim() === name) {
      return decodeURIComponent(pair.slice(separator + 1).trim());
    }
  }
  return undefined;
}

async function freshCsrfToken(): Promise<string> {
  return (await unwrap(browserApi.GET("/v1/auth/csrf"))).csrfToken;
}

/**
 * Run a state-changing call with the CSRF token. A token that no longer matches the session (it
 * was signed out elsewhere, say) is refused once, then the call is repeated with a new one.
 */
export async function withCsrf<T>(
  call: (headers: { "X-CSRF-Token": string }) => Promise<T>,
): Promise<T> {
  const token = cookieValue(CSRF_COOKIE);
  try {
    return await call({ "X-CSRF-Token": token ?? (await freshCsrfToken()) });
  } catch (error) {
    if (!(error instanceof ApiError && error.code === "CSRF_TOKEN_INVALID")) throw error;
    return call({ "X-CSRF-Token": await freshCsrfToken() });
  }
}
